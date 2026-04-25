from __future__ import annotations

from collections.abc import Callable
from importlib import import_module


SummarizerCallable = Callable[..., str]


def noop_summarizer(_: str, **__: object) -> str:
    return ""


def load_summarizer(callable_path: str | None) -> SummarizerCallable:
    if not callable_path:
        return noop_summarizer

    module_name, separator, attribute = callable_path.partition(":")
    if not separator or not module_name or not attribute:
        raise ImportError(f"Invalid summarizer callable path: {callable_path!r}")

    try:
        module = import_module(module_name)
    except Exception as exc:  # pragma: no cover - defensive import wrapping
        raise ImportError(f"Unable to import summarizer module {module_name!r}") from exc

    try:
        callable_obj = getattr(module, attribute)
    except AttributeError as exc:
        raise ImportError(f"Unable to import summarizer callable {callable_path!r}") from exc

    if not callable(callable_obj):
        raise ImportError(f"Configured summarizer is not callable: {callable_path!r}")
    return callable_obj
