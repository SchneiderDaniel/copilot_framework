from __future__ import annotations

from pathlib import Path

import pytest

from cosk.config import CoskConfig, ExtractionSettings, LanguageSettings, SummarizerSettings


@pytest.fixture
def python_language_settings() -> LanguageSettings:
    return LanguageSettings(
        name="python",
        extensions=(".py",),
        grammar_package="tree_sitter_python",
        grammar_module="language",
        query_file="python.scm",
        enabled=True,
    )


@pytest.fixture
def base_config(python_language_settings: LanguageSettings) -> CoskConfig:
    return CoskConfig(
        extraction=ExtractionSettings(
            supported_languages=(python_language_settings,),
            summarizer=SummarizerSettings(),
        )
    )


@pytest.fixture
def python_file(tmp_path: Path) -> Path:
    target = tmp_path / "sample.py"
    target.write_text(
        "def hello(name: str) -> str:\n"
        "    \"\"\"Say hello.\"\"\"\n"
        "    value = name.strip()\n"
        "    for _ in range(1):\n"
        "        value = value.upper()\n"
        "    return f'Hello {value}'\n",
        encoding="utf-8",
    )
    return target
