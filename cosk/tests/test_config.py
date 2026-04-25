from __future__ import annotations

import pytest

from cosk.config import (
    CoskConfig,
    ExtractionSettings,
    LanguageSettings,
    SummarizerSettings,
    get_cosk_config,
    validate_cosk_config,
)


def test_get_cosk_config_returns_extraction_settings() -> None:
    config = get_cosk_config()
    assert config.extraction.supported_languages


def test_config_rejects_missing_grammar_package_in_validation() -> None:
    config = CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=(
                LanguageSettings(
                    name="fake",
                    extensions=(".fake",),
                    grammar_package="missing_fake_grammar_package",
                    grammar_module="language",
                    query_file="fake.scm",
                ),
            )
        )
    )
    with pytest.raises(ImportError):
        validate_cosk_config(config)


def test_config_rejects_missing_summarizer_callable_when_configured() -> None:
    config = CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=(),
            summarizer=SummarizerSettings(callable_path="missing.module:missing"),
        )
    )
    with pytest.raises(ImportError):
        validate_cosk_config(config)


def test_config_has_no_submodule_hardcoded_language_fallbacks() -> None:
    config = get_cosk_config()
    names = [language.name for language in config.extraction.supported_languages]
    assert "python" in names
