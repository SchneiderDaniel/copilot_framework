from __future__ import annotations

from cosk.config import TopKValidationError, _parse_config, resolve_top_k


def test_resolve_top_k_none_uses_default() -> None:
    config = _parse_config({"extraction": {"supported_languages": []}, "retrieval": {"default_top_k": 7}})
    top_k, warnings = resolve_top_k(None, config)
    assert top_k == 7
    assert warnings == []


def test_resolve_top_k_clamps_and_warns() -> None:
    config = _parse_config({"extraction": {"supported_languages": []}, "retrieval": {"max_top_k": 3}})
    top_k, warnings = resolve_top_k(10, config)
    assert top_k == 3
    assert warnings


def test_resolve_top_k_rejects_non_positive() -> None:
    config = _parse_config({"extraction": {"supported_languages": []}})
    try:
        resolve_top_k(0, config)
    except TopKValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Expected TopKValidationError")

