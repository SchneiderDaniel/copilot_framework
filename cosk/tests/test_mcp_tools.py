from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cosk.config import get_cosk_config
from cosk.extraction.models import SkeletonNode
from cosk.graph.builder import compute_node_id
from cosk.indexing.vector_store import SkeletonNodeVectorStore
from cosk.mcp.server import McpError, create_mcp_server


def _node_with_signature(nodes: list[SkeletonNode], marker: str) -> SkeletonNode:
    return next(node for node in nodes if marker in node.raw_signature)


class _CountingEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str) -> list[float]:  # noqa: ARG002
        self.calls += 1
        return [1.0, 0.0]


def _kind_fixture_nodes() -> list[SkeletonNode]:
    return [
        SkeletonNode(file_path="kinds.py", start_line=1, end_line=4, raw_signature="class Service:", docstring="Service"),
        SkeletonNode(file_path="kinds.py", start_line=2, end_line=3, raw_signature="def process(self):", docstring="method"),
        SkeletonNode(file_path="kinds.py", start_line=6, end_line=7, raw_signature="def process_data():", docstring="function"),
    ]


def _build_tool_with_nodes(tmp_path: Path, nodes: list[SkeletonNode]):
    provider = _CountingEmbeddingProvider()
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    store.rebuild_index(nodes)
    mcp = create_mcp_server(store)
    return mcp._tool_manager.get_tool("cosk_search_by_name").fn, provider  # noqa: SLF001


def test_mcp_tools_registered(mcp_tools: dict[str, object]) -> None:
    assert {
        "cosk_search_by_name",
        "cosk_semantic_search",
        "cosk_get_neighbors",
        "cosk_get_symbol_source",
        "cosk_find_usage",
    } <= set(mcp_tools)


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


def test_cosk_get_symbol_source_valid_not_found_and_invalid_inputs(
    mcp_tools: dict[str, object], fixture_nodes: list[SkeletonNode]
) -> None:
    sample_node = fixture_nodes[0]
    sample_node_id = compute_node_id(sample_node)
    payload = json.loads(mcp_tools["cosk_get_symbol_source"]([sample_node_id, "missing"]))
    assert payload[0]["node_id"] == sample_node_id
    assert payload[0]["source_code"]
    assert "token_count" in payload[0]
    assert payload[1] == {"node_id": "missing", "error": "not found"}

    with pytest.raises(McpError):
        mcp_tools["cosk_get_symbol_source"]([])

    with pytest.raises(McpError):
        mcp_tools["cosk_get_symbol_source"]("not-a-list")

def test_cosk_find_usage_known_blank_and_unknown(mcp_tools: dict[str, object]) -> None:
    known = json.loads(mcp_tools["cosk_find_usage"]("helper"))
    assert known
    assert isinstance(known, list)

    with pytest.raises(McpError):
        mcp_tools["cosk_find_usage"]("   ")

    assert json.loads(mcp_tools["cosk_find_usage"]("totally_unknown_entity")) == []


def test_cosk_search_by_name_rejects_blank_query(mcp_tools: dict[str, object]) -> None:
    with pytest.raises(McpError):
        mcp_tools["cosk_search_by_name"]("  ")


def test_cosk_search_by_name_rejects_invalid_kind(mcp_tools: dict[str, object]) -> None:
    with pytest.raises(McpError):
        mcp_tools["cosk_search_by_name"]("helper", kind="module")


def test_cosk_search_by_name_substring_match_returns_expected_symbols(mcp_tools: dict[str, object]) -> None:
    payload = json.loads(mcp_tools["cosk_search_by_name"]("wrap"))
    assert any("wrapper" in entry["raw_signature"] for entry in payload)


def test_cosk_search_by_name_regex_match_returns_expected_symbols(mcp_tools: dict[str, object]) -> None:
    payload = json.loads(mcp_tools["cosk_search_by_name"]("^wrap"))
    assert any("wrapper" in entry["raw_signature"] for entry in payload)


def test_cosk_search_by_name_regex_no_match_returns_empty_array(mcp_tools: dict[str, object]) -> None:
    assert json.loads(mcp_tools["cosk_search_by_name"]("^does_not_exist$")) == []


def test_cosk_search_by_name_invalid_regex_raises_invalid_params(mcp_tools: dict[str, object]) -> None:
    with pytest.raises(McpError):
        mcp_tools["cosk_search_by_name"]("[unclosed")


def test_cosk_search_by_name_substring_no_match_returns_empty_array(mcp_tools: dict[str, object]) -> None:
    assert json.loads(mcp_tools["cosk_search_by_name"]("totally_unknown_symbol_name")) == []


def test_cosk_search_by_name_empty_index_returns_empty_array(tmp_path: Path) -> None:
    provider = _CountingEmbeddingProvider()
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    store.rebuild_index([])
    mcp = create_mcp_server(store)
    tool = mcp._tool_manager.get_tool("cosk_search_by_name").fn  # noqa: SLF001
    assert json.loads(tool("anything")) == []


def test_cosk_search_by_name_kind_function_filters_only_functions(tmp_path: Path) -> None:
    tool, _ = _build_tool_with_nodes(tmp_path, _kind_fixture_nodes())
    payload = json.loads(tool("process", kind="function"))
    assert payload and all(entry["raw_signature"].startswith("def process_data") for entry in payload)


def test_cosk_search_by_name_kind_class_filters_only_classes(tmp_path: Path) -> None:
    tool, _ = _build_tool_with_nodes(tmp_path, _kind_fixture_nodes())
    payload = json.loads(tool("service", kind="class"))
    assert payload and all(entry["raw_signature"].startswith("class Service") for entry in payload)


def test_cosk_search_by_name_kind_method_filters_only_methods(tmp_path: Path) -> None:
    tool, _ = _build_tool_with_nodes(tmp_path, _kind_fixture_nodes())
    payload = json.loads(tool("process", kind="method"))
    assert payload and all(entry["raw_signature"].startswith("def process(self)") for entry in payload)


def test_cosk_search_by_name_kind_any_includes_all_kinds(tmp_path: Path) -> None:
    tool, _ = _build_tool_with_nodes(tmp_path, _kind_fixture_nodes())
    payload = json.loads(tool("process", kind="any"))
    signatures = {entry["raw_signature"] for entry in payload}
    assert "def process(self):" in signatures
    assert "def process_data():" in signatures


def test_search_by_name_does_not_call_embedding_provider(tmp_path: Path) -> None:
    provider = _CountingEmbeddingProvider()
    nodes = _kind_fixture_nodes()
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    store.rebuild_index(nodes)
    calls_after_rebuild = provider.calls
    mcp = create_mcp_server(store)
    tool = mcp._tool_manager.get_tool("cosk_search_by_name").fn  # noqa: SLF001
    json.loads(tool("process"))
    assert provider.calls == calls_after_rebuild


def test_cosk_search_by_name_uses_resolved_store_for_index_name() -> None:
    store = SimpleNamespace(search_by_name=lambda query, kind="any": [])

    class StubManager:
        config = get_cosk_config()

        def __init__(self) -> None:
            self.calls: list[str | None] = []

        def get_context(self, *, index_name: str | None = None, db_dir: Path | None = None):  # noqa: ARG002
            self.calls.append(index_name)
            return SimpleNamespace(vector_store=store, graph=None, target_dir=None)

    manager = StubManager()
    mcp = create_mcp_server(manager=manager)
    tool = mcp._tool_manager.get_tool("cosk_search_by_name").fn  # noqa: SLF001
    assert json.loads(tool("helper", index_name="my-index")) == []
    assert manager.calls == ["my-index"]


def test_cosk_search_by_name_defaults_to_active_context_when_index_name_missing() -> None:
    store = SimpleNamespace(search_by_name=lambda query, kind="any": [])

    class StubManager:
        config = get_cosk_config()

        def __init__(self) -> None:
            self.calls: list[str | None] = []

        def get_context(self, *, index_name: str | None = None, db_dir: Path | None = None):  # noqa: ARG002
            self.calls.append(index_name)
            return SimpleNamespace(vector_store=store, graph=None, target_dir=None)

    manager = StubManager()
    mcp = create_mcp_server(manager=manager)
    tool = mcp._tool_manager.get_tool("cosk_search_by_name").fn  # noqa: SLF001
    assert json.loads(tool("helper")) == []
    assert manager.calls == [None]


def test_cosk_search_by_name_serializes_expected_result_schema(mcp_tools: dict[str, object]) -> None:
    payload = json.loads(mcp_tools["cosk_search_by_name"]("helper"))
    assert payload
    required = {"node_id", "file_path", "start_line", "end_line", "raw_signature"}
    assert required <= set(payload[0].keys())
