from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from cosk.extraction.parser import extract_skeleton_nodes
from cosk.extraction.models import SkeletonNode
from cosk.graph import state
from cosk.graph.builder import build_graph
from cosk.mcp import server as mcp_server
from cosk.mcp.server import McpError, create_mcp_server
from cosk.safety import middleware


def _tool_fn(search_results: list[dict[str, object]] | None = None):
    store = Mock()
    store.search.return_value = [] if search_results is None else search_results
    store.search_by_name.return_value = []
    mcp = create_mcp_server(store)
    tool = mcp._tool_manager.get_tool("cosk_semantic_search")  # noqa: SLF001
    return tool.fn, store


def _tool_functions():
    store = Mock()
    store.search.return_value = []
    store.search_by_name.return_value = []
    store.get_node_details.return_value = {}
    mcp = create_mcp_server(store)
    return {
        "store": store,
        "search_by_name": mcp._tool_manager.get_tool("cosk_search_by_name").fn,  # noqa: SLF001
        "semantic_search": mcp._tool_manager.get_tool("cosk_semantic_search").fn,  # noqa: SLF001
        "get_neighbors": mcp._tool_manager.get_tool("cosk_get_neighbors").fn,  # noqa: SLF001
        "get_symbol_source": mcp._tool_manager.get_tool("cosk_get_symbol_source").fn,  # noqa: SLF001
        "find_usage": mcp._tool_manager.get_tool("cosk_find_usage").fn,  # noqa: SLF001
    }


@pytest.fixture(autouse=True)
def _clear_graph_state() -> None:
    state.clear_graph()
    middleware._registry.clear()  # noqa: SLF001


def test_server_module_docstring_contains_cli_usage_args_and_error_behavior() -> None:
    import cosk.mcp.server as server_module

    doc = server_module.__doc__ or ""
    assert "python -m cosk.mcp.server" in doc
    assert "--target-dir" in doc
    assert "--db-dir" in doc
    assert "Startup" in doc
    assert "Tool" in doc


@pytest.mark.parametrize("query", ["", "   "])
def test_cosk_semantic_search_rejects_blank_query_as_mcp_tool_error(query: str) -> None:
    tool_fn, _ = _tool_fn()
    with pytest.raises(McpError):
        tool_fn(query)


def test_cosk_semantic_search_serializes_results_as_json_text_array() -> None:
    results = [
        {
            "node_id": "1",
            "file_path": "a.py",
            "start_line": 1,
            "end_line": 2,
            "raw_signature": "def a()",
            "summary": "A",
        },
        {
            "node_id": "2",
            "file_path": "b.py",
            "start_line": 3,
            "end_line": 4,
            "raw_signature": "def b()",
            "summary": "B",
        },
    ]
    tool_fn, _ = _tool_fn(results)
    serialized = tool_fn("query")
    parsed = json.loads(serialized)
    assert isinstance(parsed, list)
    assert parsed[0]["node_id"] == results[0]["node_id"]
    assert "graph_node_id" in parsed[0]
    assert "token_count" in parsed[0]


def test_cosk_semantic_search_defaults_top_k_to_5() -> None:
    tool_fn, store = _tool_fn()
    tool_fn("find me")
    store.search.assert_called_once_with("find me", top_k=5)


def test_cosk_semantic_search_accepts_optional_top_k() -> None:
    tool_fn, store = _tool_fn()
    tool_fn("find me", top_k=2)
    store.search.assert_called_once_with("find me", top_k=2)


def test_cosk_semantic_search_invalid_top_k_raises_mcp_error() -> None:
    tool_fn, _ = _tool_fn()
    with pytest.raises(McpError):
        tool_fn("find me", top_k=0)


def test_cosk_semantic_search_returns_empty_array_for_empty_index() -> None:
    tool_fn, _ = _tool_fn([])
    assert json.loads(tool_fn("query")) == []


def test_create_mcp_server_registers_all_tools() -> None:
    store = Mock()
    store.search.return_value = []
    store.search_by_name.return_value = []
    mcp = create_mcp_server(store)
    assert mcp._tool_manager.get_tool("cosk_search_by_name") is not None  # noqa: SLF001
    assert mcp._tool_manager.get_tool("cosk_semantic_search") is not None  # noqa: SLF001
    assert mcp._tool_manager.get_tool("cosk_get_neighbors") is not None  # noqa: SLF001
    assert mcp._tool_manager.get_tool("cosk_get_symbol_source") is not None  # noqa: SLF001
    assert mcp._tool_manager.get_tool("cosk_find_usage") is not None  # noqa: SLF001


def test_create_mcp_server_registers_cosk_search_by_name() -> None:
    store = Mock()
    store.search.return_value = []
    store.search_by_name.return_value = []
    mcp = create_mcp_server(store)
    assert mcp._tool_manager.get_tool("cosk_search_by_name") is not None  # noqa: SLF001


def test_cosk_semantic_search_behavior_unchanged_with_optional_ctx_parameter() -> None:
    tool_fn, store = _tool_fn(
        [
            {
                "node_id": "1",
                "file_path": "a.py",
                "start_line": 1,
                "end_line": 1,
                "raw_signature": "def a()",
                "summary": "",
            }
        ]
    )
    payload = json.loads(tool_fn("query", ctx=None))
    assert payload[0]["file_path"] == "a.py"
    store.search.assert_called_once_with("query", top_k=5)


def test_enrich_search_results_never_returns_empty_summary() -> None:
    enriched, warnings = mcp_server.enrich_search_results(
        [
            {
                "node_id": "1",
                "file_path": "a.py",
                "start_line": 1,
                "end_line": 2,
                "raw_signature": "def alpha()",
                "summary": "   ",
            }
        ]
    )
    assert warnings == []
    assert enriched[0]["summary"] == "def alpha()"


def test_search_and_neighbors_do_not_emit_tiktoken_missing_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_server,
        "estimate_with_warnings",
        lambda _text: (None, ["tiktoken is not installed; token_count is unavailable."]),
    )
    search_results, search_warnings = mcp_server.enrich_search_results(
        [
            {
                "node_id": "1",
                "file_path": "a.py",
                "start_line": 1,
                "end_line": 1,
                "raw_signature": "def alpha()",
                "summary": "",
            }
        ]
    )
    assert search_results[0]["summary"] == "def alpha()"
    assert search_warnings == []

    store = Mock()
    store.get_node_details.return_value = {
        "a.py:1": {"raw_signature": "def alpha()", "summary": ""},
    }
    neighbors, neighbor_warnings = mcp_server.enrich_neighbor_entries(
        store,
        {"inbound": [{"node_id": "a.py:1", "label": "calls"}], "outbound": []},
    )
    assert neighbors["inbound"][0]["summary"] == "def alpha()"
    assert neighbor_warnings == []


@pytest.mark.parametrize("node_id", ["", "   "])
def test_cosk_get_neighbors_rejects_blank_node_id_as_mcp_tool_error(node_id: str) -> None:
    with pytest.raises(McpError):
        _tool_functions()["get_neighbors"](node_id)


def test_cosk_get_neighbors_returns_neighbors_json_for_known_node() -> None:
    nodes = [
        SkeletonNode(
            file_path="module_a.py",
            start_line=1,
            end_line=1,
            raw_signature="def callee():",
            docstring="",
        ),
        SkeletonNode(
            file_path="module_b.py",
            start_line=1,
            end_line=2,
            raw_signature="def caller():\n    callee()",
            docstring="",
        ),
    ]
    graph = build_graph(nodes)
    state.set_graph(graph)
    result = _tool_functions()["get_neighbors"](" module_b.py:1 ")
    parsed = json.loads(result)
    assert set(parsed) == {"inbound", "outbound"}
    assert isinstance(parsed["inbound"], list)
    assert isinstance(parsed["outbound"], list)
    assert parsed["outbound"]
    for entry in parsed["outbound"]:
        assert isinstance(entry["node_id"], str)
        assert isinstance(entry["label"], str)


def test_cosk_get_neighbors_returns_empty_lists_for_unknown_node() -> None:
    nodes = [
        SkeletonNode(
            file_path="module_a.py",
            start_line=1,
            end_line=1,
            raw_signature="def callee():",
            docstring="",
        )
    ]
    state.set_graph(build_graph(nodes))
    parsed = json.loads(_tool_functions()["get_neighbors"]("missing.py:99"))
    assert parsed == {"inbound": [], "outbound": []}


def test_cosk_get_neighbors_raises_mcp_error_when_graph_not_loaded() -> None:
    state.clear_graph()
    with pytest.raises(McpError, match="cosk_get_neighbors failed: relationship graph is not loaded"):
        _tool_functions()["get_neighbors"]("module.py:1")


def test_cosk_get_neighbors_wraps_runtime_failures_as_internal_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenGraph:
        def get_neighbors(self, node_id: str):  # noqa: ARG002
            raise RuntimeError("boom")

    monkeypatch.setattr(state, "get_graph", lambda: BrokenGraph())
    with pytest.raises(McpError, match="cosk_get_neighbors failed:"):
        _tool_functions()["get_neighbors"]("module.py:1")


@pytest.mark.parametrize("entity_name", ["", "   "])
def test_cosk_find_usage_rejects_blank_entity_name_as_mcp_tool_error(entity_name: str) -> None:
    with pytest.raises(McpError):
        _tool_functions()["find_usage"](entity_name)


def test_cosk_find_usage_raises_mcp_error_when_graph_not_loaded() -> None:
    state.clear_graph()
    with pytest.raises(McpError, match="cosk_find_usage failed: relationship graph is not loaded"):
        _tool_functions()["find_usage"]("foo")


def test_cosk_find_usage_returns_empty_json_array_for_unknown_entity() -> None:
    nodes = [
        SkeletonNode(
            file_path="module_a.py",
            start_line=1,
            end_line=1,
            raw_signature="def callee():",
            docstring="",
        )
    ]
    state.set_graph(build_graph(nodes))
    result = _tool_functions()["find_usage"]("nonexistent")
    assert json.loads(result) == []


def test_cosk_find_usage_returns_results_for_known_entity() -> None:
    nodes = [
        SkeletonNode(
            file_path="callee.py",
            start_line=1,
            end_line=1,
            raw_signature="def foo():",
            docstring="",
        ),
        SkeletonNode(
            file_path="caller.py",
            start_line=5,
            end_line=5,
            raw_signature="def bar(x=foo()):",
            docstring="",
        ),
    ]
    state.set_graph(build_graph(nodes))
    result = json.loads(_tool_functions()["find_usage"]("foo"))
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["file_path"] == "caller.py"
    assert result[0]["line"] == 5
    assert "context_node_id" in result[0]


def test_cosk_find_usage_result_contains_required_fields() -> None:
    nodes = [
        SkeletonNode(file_path="callee.py", start_line=1, end_line=1, raw_signature="def foo():", docstring=""),
        SkeletonNode(file_path="caller.py", start_line=5, end_line=5, raw_signature="def bar(x=foo()):", docstring=""),
    ]
    state.set_graph(build_graph(nodes))
    result = json.loads(_tool_functions()["find_usage"]("foo"))
    assert result
    assert set(result[0]) == {"file_path", "line", "context_node_id"}


def test_cosk_find_usage_returns_real_forestrag_backend_file_line_pair() -> None:
    backend_dir = Path(__file__).resolve().parents[2] / "forestrag" / "backend"
    state.set_graph(build_graph(extract_skeleton_nodes(backend_dir)))
    result = json.loads(_tool_functions()["find_usage"]("Depends"))
    assert result
    assert any(entry["file_path"].endswith("forestrag/backend/entities/router.py") for entry in result)
    assert any(entry["file_path"].endswith("forestrag/backend/entities/router.py") and entry["line"] == 50 for entry in result)


def test_cosk_find_usage_wraps_runtime_failures_as_internal_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenGraph:
        def find_usages(self, entity_name: str):  # noqa: ARG002
            raise RuntimeError("boom")

    monkeypatch.setattr(state, "get_graph", lambda: BrokenGraph())
    with pytest.raises(McpError, match="cosk_find_usage failed:"):
        _tool_functions()["find_usage"]("foo")


def test_cosk_get_symbol_source_returns_exact_inclusive_source_for_known_node_id(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.py"
    lines = ["line 1\n", "line 2\n", "line 3\n", "line 4\n", "line 5\n"]
    source_file.write_text("".join(lines), encoding="utf-8")
    tools = _tool_functions()
    tools["store"].get_node_details.return_value = {
        "known": {
            "file_path": str(source_file),
            "start_line": 2,
            "end_line": 4,
            "raw_signature": "def known():",
        }
    }
    payload = json.loads(tools["get_symbol_source"](["known"]))
    assert len(payload) == 1
    assert payload[0]["node_id"] == "known"
    assert payload[0]["file_path"] == str(source_file)
    assert payload[0]["start_line"] == 2
    assert payload[0]["end_line"] == 4
    assert payload[0]["raw_signature"] == "def known():"
    assert payload[0]["source_code"] == "".join(lines[1:4])
    assert "token_count" in payload[0]


def test_cosk_get_symbol_source_returns_not_found_and_continues_batch(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.py"
    source_file.write_text("alpha\nbeta\n", encoding="utf-8")
    tools = _tool_functions()
    tools["store"].get_node_details.return_value = {
        "known": {"file_path": str(source_file), "start_line": 1, "end_line": 1, "raw_signature": "def known():"}
    }
    payload = json.loads(tools["get_symbol_source"](["known", "missing"]))
    assert payload[0]["node_id"] == "known"
    assert payload[0]["source_code"] == "alpha\n"
    assert payload[1] == {"node_id": "missing", "error": "not found"}


def test_cosk_get_symbol_source_returns_sandbox_error_for_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("print('x')\n", encoding="utf-8")
    store = Mock()
    store.search.return_value = []
    store.search_by_name.return_value = []
    store.get_node_details.return_value = {
        "outside": {
            "file_path": str(outside_file),
            "start_line": 1,
            "end_line": 1,
            "raw_signature": "print('x')",
        }
    }

    class _Manager:
        config = None

        def get_context(self, *, index_name: str | None = None, db_dir: Path | None = None):  # noqa: ARG002
            return Mock(vector_store=store, target_dir=root, manifest=None, graph=None)

    mcp = create_mcp_server(manager=_Manager())
    get_symbol_source = mcp._tool_manager.get_tool("cosk_get_symbol_source").fn  # noqa: SLF001
    payload = json.loads(get_symbol_source(["outside"]))
    assert payload == [{"node_id": "outside", "error": "path is outside indexed root"}]


def test_cosk_get_symbol_source_rejects_empty_node_ids_with_invalid_params() -> None:
    with pytest.raises(McpError):
        _tool_functions()["get_symbol_source"]([])


def test_cosk_get_symbol_source_rejects_non_list_node_ids_with_invalid_params() -> None:
    with pytest.raises(McpError):
        _tool_functions()["get_symbol_source"]("not-a-list")


def test_cosk_get_symbol_source_preserves_input_order_and_duplicates(tmp_path: Path) -> None:
    source_a = tmp_path / "a.py"
    source_b = tmp_path / "b.py"
    source_a.write_text("a1\na2\n", encoding="utf-8")
    source_b.write_text("b1\nb2\n", encoding="utf-8")
    tools = _tool_functions()
    tools["store"].get_node_details.return_value = {
        "id_a": {"file_path": str(source_a), "start_line": 1, "end_line": 1, "raw_signature": "def a():"},
        "id_b": {"file_path": str(source_b), "start_line": 2, "end_line": 2, "raw_signature": "def b():"},
    }
    payload = json.loads(tools["get_symbol_source"](["id_a", "missing", "id_a", "id_b"]))
    assert [entry["node_id"] for entry in payload] == ["id_a", "missing", "id_a", "id_b"]
    assert payload[1] == {"node_id": "missing", "error": "not found"}


def test_cosk_get_symbol_source_calls_get_node_details_once_per_request(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.py"
    source_file.write_text("alpha\n", encoding="utf-8")
    tools = _tool_functions()
    tools["store"].get_node_details.return_value = {
        "known": {"file_path": str(source_file), "start_line": 1, "end_line": 1, "raw_signature": "def known():"}
    }
    json.loads(tools["get_symbol_source"](["known", "missing"]))
    tools["store"].get_node_details.assert_called_once_with(["known", "missing"])


def test_cosk_get_symbol_source_returns_error_for_incomplete_metadata() -> None:
    tools = _tool_functions()
    tools["store"].get_node_details.return_value = {"broken": {"file_path": "x.py", "start_line": 1}}
    payload = json.loads(tools["get_symbol_source"](["broken"]))
    assert payload == [{"node_id": "broken", "error": "metadata is incomplete"}]


def test_cosk_find_usage_behavior_unchanged_with_middleware_present() -> None:
    nodes = [
        SkeletonNode(file_path="callee.py", start_line=1, end_line=1, raw_signature="def foo():", docstring=""),
        SkeletonNode(file_path="caller.py", start_line=5, end_line=5, raw_signature="def bar(x=foo()):", docstring=""),
    ]
    state.set_graph(build_graph(nodes))
    result = json.loads(_tool_functions()["find_usage"]("foo"))
    assert result and result[0]["file_path"] == "caller.py"


def test_enrich_search_results_never_returns_empty_summary() -> None:
    enriched, warnings = mcp_server.enrich_search_results(
        [
            {
                "node_id": "n1",
                "file_path": "a.py",
                "start_line": 1,
                "end_line": 1,
                "raw_signature": "def alpha()",
                "summary": "",
            }
        ]
    )
    assert warnings == []
    assert enriched[0]["summary"] == "def alpha()"


@pytest.mark.parametrize(
    ("fn_name", "args"),
    [
        ("enrich_search_results", [[{"node_id": "n", "file_path": "a.py", "start_line": 1, "end_line": 1, "raw_signature": "def a()", "summary": ""}]]),
        ("enrich_neighbor_entries", [Mock(get_node_details=lambda _ids: {"n": {"raw_signature": "def a()", "summary": ""}}), {"inbound": [{"node_id": "n", "label": "calls"}], "outbound": []}]),
    ],
)
def test_search_and_neighbors_do_not_emit_tiktoken_missing_warnings(monkeypatch: pytest.MonkeyPatch, fn_name: str, args: list[object]) -> None:
    monkeypatch.setattr(mcp_server, "estimate_with_warnings", lambda _text: (None, []))
    _, warnings = getattr(mcp_server, fn_name)(*args)
    assert warnings == []
