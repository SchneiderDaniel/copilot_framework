from __future__ import annotations

from importlib.resources import files
import warnings


def load_query_text(query_file: str, *, strict: bool) -> str | None:
    query_path = files("cosk.extraction").joinpath("queries", query_file)
    if not query_path.is_file():
        if strict:
            raise FileNotFoundError(f"Missing tree-sitter query file: {query_file}")
        warnings.warn(f"Skipping language due to missing query file: {query_file}", RuntimeWarning, stacklevel=2)
        return None
    return query_path.read_text(encoding="utf-8")
