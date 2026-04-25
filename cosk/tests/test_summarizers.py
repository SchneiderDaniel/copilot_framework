from __future__ import annotations

import pytest

from cosk.extraction.summarizers import load_summarizer, noop_summarizer


def test_default_noop_summarizer_returns_empty_string() -> None:
    assert noop_summarizer("x", file_path="a.py", language="python") == ""


def test_summarizer_loader_imports_configured_callable() -> None:
    summarizer = load_summarizer("cosk.extraction.summarizers:noop_summarizer")
    assert summarizer("x", file_path="a.py", language="python") == ""


def test_summarizer_loader_raises_for_invalid_callable_path() -> None:
    with pytest.raises(ImportError):
        load_summarizer("bad.path:missing")
