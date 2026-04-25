from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import import_module
from importlib.util import find_spec


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
    exclude_dirs: tuple[str, ...] = ("__pycache__", ".git", "node_modules", ".venv")
    follow_symlinks: bool = False
    strict: bool = False
    summarizer: SummarizerSettings = field(default_factory=SummarizerSettings)


@dataclass
class CoskConfig:
    extraction: ExtractionSettings


_DEFAULT_LANGUAGE_SPECS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("python", (".py",), "tree_sitter_python"),
    ("javascript", (".js", ".mjs", ".cjs"), "tree_sitter_javascript"),
    ("typescript", (".ts", ".tsx"), "tree_sitter_typescript"),
    ("java", (".java",), "tree_sitter_java"),
    ("go", (".go",), "tree_sitter_go"),
    ("rust", (".rs",), "tree_sitter_rust"),
    ("c", (".c", ".h"), "tree_sitter_c"),
    ("cpp", (".cpp", ".cxx", ".cc", ".hpp"), "tree_sitter_cpp"),
    ("ruby", (".rb",), "tree_sitter_ruby"),
    ("bash", (".sh", ".bash"), "tree_sitter_bash"),
    ("json", (".json",), "tree_sitter_json"),
    ("yaml", (".yaml", ".yml"), "tree_sitter_yaml"),
    ("toml", (".toml",), "tree_sitter_toml"),
    ("css", (".css",), "tree_sitter_css"),
    ("html", (".html", ".htm"), "tree_sitter_html"),
    ("kotlin", (".kt", ".kts"), "tree_sitter_kotlin"),
    ("lua", (".lua",), "tree_sitter_lua"),
    ("markdown", (".md",), "tree_sitter_markdown"),
    ("php", (".php",), "tree_sitter_php"),
    ("scala", (".scala",), "tree_sitter_scala"),
    ("sql", (".sql",), "tree_sitter_sql"),
    ("swift", (".swift",), "tree_sitter_swift"),
    ("c-sharp", (".cs",), "tree_sitter_c_sharp"),
)


def _build_default_languages() -> tuple[LanguageSettings, ...]:
    return tuple(
        LanguageSettings(
            name=name,
            extensions=extensions,
            grammar_package=grammar_package,
            grammar_module="language",
            query_file=f"{name}.scm",
            enabled=find_spec(grammar_package) is not None,
        )
        for name, extensions, grammar_package in _DEFAULT_LANGUAGE_SPECS
    )


@lru_cache(maxsize=1)
def get_cosk_config() -> CoskConfig:
    return CoskConfig(extraction=ExtractionSettings(supported_languages=_build_default_languages()))


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
