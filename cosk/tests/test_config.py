from __future__ import annotations

import pytest

from cosk.config import (
    CoskConfig,
    ExtractionSettings,
    LanguageSettings,
    SummarizerSettings,
    _parse_config,
    get_cosk_config,
    get_cosk_config as _get_cosk_config,
    resolve_top_k,
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


def test_extraction_settings_respect_gitignore_defaults_true() -> None:
    config = get_cosk_config()
    assert config.extraction.respect_gitignore is True


def test_parse_config_reads_respect_gitignore_false() -> None:
    parsed = _parse_config(
        {
            "extraction": {
                "supported_languages": [],
                "respect_gitignore": False,
            }
        }
    )
    assert parsed.extraction.respect_gitignore is False


def test_cosk_max_top_k_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSK_MAX_TOP_K", "2")
    _get_cosk_config.cache_clear()
    config = get_cosk_config()
    top_k, warnings = resolve_top_k(9, config)
    assert top_k == 2
    assert warnings
    _get_cosk_config.cache_clear()
