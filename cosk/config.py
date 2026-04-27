from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import import_module
from importlib.util import find_spec
import os
from pathlib import Path

import yaml

_SETTINGS_PATH = Path(__file__).parent / "config" / "cosk.settings.yaml"


@dataclass
class SummarizerSettings:
    callable_path: str | None = None
    kwargs: dict = field(default_factory=dict)


@dataclass
class LanguageSettings:
    name: str
    extensions: tuple[str, ...]
    grammar_package: str
    grammar_module: str
    query_file: str
    enabled: bool = True


@dataclass
class ExtractionSettings:
    supported_languages: tuple[LanguageSettings, ...]
    source_directory: str = "."
    exclude_dirs: tuple[str, ...] = ("__pycache__", ".git", "node_modules", ".venv")
    follow_symlinks: bool = False
    strict: bool = False
    respect_gitignore: bool = True
    summarizer: SummarizerSettings = field(default_factory=SummarizerSettings)


@dataclass
class RetrievalSettings:
    default_top_k: int = 5
    max_top_k: int = 20


@dataclass
class TransportSettings:
    http_host: str = "127.0.0.1"
    http_port: int = 8765


@dataclass
class CoskConfig:
    extraction: ExtractionSettings
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    transport: TransportSettings = field(default_factory=TransportSettings)


class TopKValidationError(ValueError):
    """Raised when top_k is invalid."""


def _parse_config(data: dict) -> CoskConfig:
    ext = data.get("extraction", {})
    retrieval_data = data.get("retrieval", {}) or {}
    transport_data = data.get("transport", {}) or {}
    summarizer_data = ext.get("summarizer", {}) or {}
    summarizer = SummarizerSettings(
        callable_path=summarizer_data.get("callable_path"),
        kwargs=summarizer_data.get("kwargs") or {},
    )
    languages = tuple(
        LanguageSettings(
            name=lang["name"],
            extensions=tuple(lang["extensions"]),
            grammar_package=lang["grammar_package"],
            grammar_module=lang.get("grammar_module", "language"),
            query_file=lang["query_file"],
            enabled=lang.get("enabled", True) and find_spec(lang["grammar_package"]) is not None,
        )
        for lang in ext.get("supported_languages", [])
    )
    return CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=languages,
            source_directory=ext.get("source_directory", "."),
            exclude_dirs=tuple(ext.get("exclude_dirs", ("__pycache__", ".git", "node_modules", ".venv"))),
            follow_symlinks=ext.get("follow_symlinks", False),
            strict=ext.get("strict", False),
            respect_gitignore=ext.get("respect_gitignore", True),
            summarizer=summarizer,
        ),
        retrieval=RetrievalSettings(
            default_top_k=int(retrieval_data.get("default_top_k", 5)),
            max_top_k=int(retrieval_data.get("max_top_k", 20)),
        ),
        transport=TransportSettings(
            http_host=str(transport_data.get("http_host", "127.0.0.1")),
            http_port=int(transport_data.get("http_port", 8765)),
        ),
    )


@lru_cache(maxsize=1)
def get_cosk_config() -> CoskConfig:
    with _SETTINGS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    config = _parse_config(data)
    max_top_k_from_env = os.getenv("COSK_MAX_TOP_K")
    if max_top_k_from_env is not None:
        config.retrieval.max_top_k = int(max_top_k_from_env)
    return config


def resolve_top_k(requested: int | None, config: CoskConfig) -> tuple[int, list[str]]:
    warnings: list[str] = []
    if requested is None:
        return config.retrieval.default_top_k, warnings
    if not isinstance(requested, int):
        raise TopKValidationError("top_k must be an integer")
    if requested <= 0:
        raise TopKValidationError("top_k must be > 0")
    if requested > config.retrieval.max_top_k:
        warnings.append(
            f"Requested top_k={requested} exceeded max_top_k={config.retrieval.max_top_k}; clamped."
        )
        return config.retrieval.max_top_k, warnings
    return requested, warnings


def validate_cosk_config(config: CoskConfig) -> None:
    from cosk.extraction.summarizers import load_summarizer

    for language in config.extraction.supported_languages:
        if not language.enabled:
            continue
        module = import_module(language.grammar_package)
        if not hasattr(module, language.grammar_module):
            raise ImportError(
                f"Grammar module '{language.grammar_module}' not found in package '{language.grammar_package}'."
            )
    if config.extraction.summarizer.callable_path:
        load_summarizer(config.extraction.summarizer.callable_path)
