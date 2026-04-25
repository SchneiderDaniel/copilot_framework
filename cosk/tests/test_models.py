from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cosk.extraction.models import SkeletonNode


def test_skeleton_node_is_frozen_and_slotted() -> None:
    node = SkeletonNode("a.py", 1, 2, "def a():", "")
    with pytest.raises(FrozenInstanceError):
        node.file_path = "b.py"  # type: ignore[misc]

    with pytest.raises((AttributeError, TypeError)):
        node.extra = "x"  # type: ignore[attr-defined]


def test_skeleton_node_fields_match_schema_contract() -> None:
    node = SkeletonNode("a.py", 1, 2, "def a():", "doc")
    assert tuple(node.__dataclass_fields__.keys()) == (
        "file_path",
        "start_line",
        "end_line",
        "raw_signature",
        "docstring",
    )
