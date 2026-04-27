from __future__ import annotations

from cosk.token_estimation import estimate_with_warnings


def test_empty_text_is_zero_tokens() -> None:
    count, warnings = estimate_with_warnings("")
    assert count in (0, None)
    assert isinstance(warnings, list)


def test_nonfatal_when_dependency_missing() -> None:
    count, warnings = estimate_with_warnings("hello world")
    assert count is None or count >= 0
    assert isinstance(warnings, list)

