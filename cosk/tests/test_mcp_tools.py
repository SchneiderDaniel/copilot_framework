from __future__ import annotations

import json

import pytest

from cosk.extraction.models import SkeletonNode
from cosk.graph.builder import compute_node_id
from cosk.mcp.server import McpError


def _node_with_signature(nodes: list[SkeletonNode], marker: str) -> SkeletonNode:
    return next(node for node in nodes if marker in node.raw_signature)


def test_mcp_tools_registered(mcp_tools: dict[str, object]) -> None:
    assert {"cosk_semantic_search", "cosk_get_neighbors", "cosk_expand_definition", "cosk_find_usage"} <= set(mcp_tools)


def test_cosk_semantic_search_valid_and_blank_error(mcp_tools: dict[str, object]) -> None:
    valid_response = mcp_tools["cosk_semantic_search"]("wrapper")
    payload = json.loads(valid_response)
    assert isinstance(payload, list)
    assert payload

    with pytest.raises(McpError):
        mcp_tools["cosk_semantic_search"]("   ")


def test_cosk_get_neighbors_valid_blank_and_missing(
    mcp_tools: dict[str, object], fixture_nodes: list[SkeletonNode]
) -> None:
    wrapper_node = _node_with_signature(fixture_nodes, "def wrapper(")
    parsed_valid = json.loads(mcp_tools["cosk_get_neighbors"](compute_node_id(wrapper_node)))
    assert set(parsed_valid) == {"inbound", "outbound"}
    assert parsed_valid["inbound"] or parsed_valid["outbound"]

    with pytest.raises(McpError):
        mcp_tools["cosk_get_neighbors"]("   ")

    assert json.loads(mcp_tools["cosk_get_neighbors"]("missing.py:999")) == {"inbound": [], "outbound": []}


def test_cosk_expand_definition_valid_blank_invalid_and_missing_file(
    mcp_tools: dict[str, object], fixture_nodes: list[SkeletonNode], tmp_path
) -> None:
    sample_node = fixture_nodes[0]
    valid_source = mcp_tools["cosk_expand_definition"](sample_node.file_path, sample_node.start_line, sample_node.end_line)
    assert valid_source
    assert "def " in valid_source

    with pytest.raises(McpError):
        mcp_tools["cosk_expand_definition"]("   ", 1, 1)

    with pytest.raises(McpError):
        mcp_tools["cosk_expand_definition"]("x.py", 0, 1)

    with pytest.raises(McpError):
        mcp_tools["cosk_expand_definition"]("x.py", 2, 1)

    missing_path = tmp_path / "missing.py"
    missing_file_result = mcp_tools["cosk_expand_definition"](str(missing_path), 1, 1)
    assert isinstance(missing_file_result, str)
    assert str(missing_path) in missing_file_result


def test_cosk_find_usage_known_blank_and_unknown(
    mcp_tools: dict[str, object],
) -> None:
    known = json.loads(mcp_tools["cosk_find_usage"]("helper"))
    assert known
    assert isinstance(known, list)

    with pytest.raises(McpError):
        mcp_tools["cosk_find_usage"]("   ")

    assert json.loads(mcp_tools["cosk_find_usage"]("totally_unknown_entity")) == []
