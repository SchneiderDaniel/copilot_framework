from __future__ import annotations

import pytest

from cosk.config import CoskConfig, ExtractionSettings, LanguageSettings
from cosk.extraction.registry import build_extension_registry


def test_registry_builds_extension_to_language_map_from_config() -> None:
    config = CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=(
                LanguageSettings(
                    name="python",
                    extensions=(".py",),
                    grammar_package="tree_sitter_python",
                    grammar_module="language",
                    query_file="python.scm",
                ),
            )
        )
    )
    registry = build_extension_registry(config)
    assert registry[".py"].name == "python"


def test_registry_ignores_disabled_languages() -> None:
    config = CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=(
                LanguageSettings(
                    name="python",
                    extensions=(".py",),
                    grammar_package="tree_sitter_python",
                    grammar_module="language",
                    query_file="python.scm",
                    enabled=False,
                ),
            )
        )
    )
    assert build_extension_registry(config) == {}


def test_registry_duplicate_extension_conflict_raises() -> None:
    config = CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=(
                LanguageSettings(
                    name="a",
                    extensions=(".py",),
                    grammar_package="tree_sitter_python",
                    grammar_module="language",
                    query_file="python.scm",
                ),
                LanguageSettings(
                    name="b",
                    extensions=(".py",),
                    grammar_package="tree_sitter_python",
                    grammar_module="language",
                    query_file="python.scm",
                ),
            )
        )
    )
    with pytest.raises(ValueError):
        build_extension_registry(config)
