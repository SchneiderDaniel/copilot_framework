from __future__ import annotations

from cosk.extraction.models import SkeletonNode
from cosk.extraction.parser import skeleton_nodes_to_json


def test_skeleton_nodes_to_json_exact_five_fields() -> None:
    payload = skeleton_nodes_to_json([SkeletonNode("a.py", 1, 2, "def a():", "")])
    assert set(payload[0].keys()) == {"file_path", "start_line", "end_line", "raw_signature", "docstring"}


def test_skeleton_nodes_to_json_field_types() -> None:
    payload = skeleton_nodes_to_json([SkeletonNode("a.py", 1, 2, "def a():", "")])[0]
    assert isinstance(payload["file_path"], str)
    assert isinstance(payload["start_line"], int)
    assert isinstance(payload["end_line"], int)
    assert isinstance(payload["raw_signature"], str)
    assert isinstance(payload["docstring"], str)


def test_skeleton_nodes_to_json_empty_list() -> None:
    assert skeleton_nodes_to_json([]) == []
