from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkeletonNode:
    file_path: str
    start_line: int
    end_line: int
    raw_signature: str
    docstring: str
