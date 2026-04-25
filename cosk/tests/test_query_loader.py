from __future__ import annotations

import pytest

from cosk.extraction.query_loader import load_query_text


def test_query_loader_resolves_packaged_scm_file() -> None:
    text = load_query_text("python.scm", strict=True)
    assert "@definition" in text


def test_query_loader_missing_file_strict_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_query_text("does_not_exist.scm", strict=True)


def test_query_loader_missing_file_non_strict_warns_and_skips(recwarn: pytest.WarningsRecorder) -> None:
    assert load_query_text("does_not_exist.scm", strict=False) is None
    assert recwarn
