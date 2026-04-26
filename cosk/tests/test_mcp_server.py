from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from cosk.extraction.parser import extract_skeleton_nodes
from cosk.extraction.models import SkeletonNode
from cosk.graph import state
from cosk.graph.builder import build_graph
from cosk.mcp.server import McpError, create_mcp_server
from cosk.safety import middleware


def _tool_fn(search_results: list[dict[str, object]] | None = None):
    store = Mock()
    store.search.return_value = [] if search_results is None else search_results
    mcp = create_mcp_server(store)
    tool = mcp._tool_manager.get_tool("cosk_semantic_search")  # noqa: SLF001
    return tool.fn, store


def _tool_functions():
    store = Mock()
    store.search.return_value = []
    mcp = create_mcp_server(store)
    return {
        "semantic_search": mcp._tool_manager.get_tool("cosk_semantic_search").fn,  # noqa: SLF001
        "get_neighbors": mcp._tool_manager.get_tool("cosk_get_neighbors").fn,  # noqa: SLF001
        "expand_definition": mcp._tool_manager.get_tool("cosk_expand_definition").fn,  # noqa: SLF001
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
    assert parsed == results


def test_cosk_semantic_search_limits_top_k_to_5() -> None:
    tool_fn, store = _tool_fn()
    tool_fn("find me")
    store.search.assert_called_once_with("find me", top_k=5)


def test_cosk_semantic_search_returns_empty_array_for_empty_index() -> None:
    tool_fn, _ = _tool_fn([])
    assert json.loads(tool_fn("query")) == []


def test_create_mcp_server_registers_all_tools() -> None:
    store = Mock()
    store.search.return_value = []
    mcp = create_mcp_server(store)
    assert mcp._tool_manager.get_tool("cosk_semantic_search") is not None  # noqa: SLF001
    assert mcp._tool_manager.get_tool("cosk_get_neighbors") is not None  # noqa: SLF001
    assert mcp._tool_manager.get_tool("cosk_expand_definition") is not None  # noqa: SLF001
    assert mcp._tool_manager.get_tool("cosk_find_usage") is not None  # noqa: SLF001


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


@pytest.mark.parametrize("file_path", ["", "   "])
def test_cosk_expand_definition_rejects_blank_file_path_as_mcp_tool_error(file_path: str) -> None:
    with pytest.raises(McpError):
        _tool_functions()["expand_definition"](file_path, 1, 1)


@pytest.mark.parametrize(("start_line", "end_line"), [(0, 1), (-1, 1), (3, 2)])
def test_cosk_expand_definition_rejects_invalid_line_ranges_as_mcp_tool_error(start_line: int, end_line: int) -> None:
    with pytest.raises(McpError):
        _tool_functions()["expand_definition"]("dummy.py", start_line, end_line)


def test_cosk_expand_definition_returns_inclusive_raw_source_range(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.py"
    lines = ["line 1\n", "line 2\n", "line 3\n", "line 4\n", "line 5\n"]
    source_file.write_text("".join(lines), encoding="utf-8")
    result = _tool_functions()["expand_definition"](str(source_file), 2, 4)
    assert result == "".join(lines[1:4])


def test_cosk_expand_definition_returns_descriptive_string_for_missing_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.py"
    result = _tool_functions()["expand_definition"](str(missing_file), 1, 2)
    assert isinstance(result, str)
    assert str(missing_file) in result


def test_cosk_expand_definition_returns_descriptive_string_for_out_of_range_request(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.py"
    source_file.write_text("a\nb\n", encoding="utf-8")
    result = _tool_functions()["expand_definition"](str(source_file), 2, 5)
    assert result == "Requested line range 2-5 is outside file bounds; file has 2 lines."


def test_cosk_expand_definition_behavior_unchanged_with_optional_ctx_parameter(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.py"
    source_file.write_text("line 1\nline 2\n", encoding="utf-8")
    result = _tool_functions()["expand_definition"](str(source_file), 1, 2, ctx=None)
    assert result == "line 1\nline 2\n"


def test_cosk_expand_definition_uses_builtin_open_for_file_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_paths: list[str] = []

    class _FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def readlines(self):
            return ["alpha\n", "beta\n", "gamma\n"]

    def _open_spy(path: str, mode: str = "r", encoding: str | None = None):  # noqa: ARG001
        opened_paths.append(path)
        return _FakeFile()

    monkeypatch.setattr("builtins.open", _open_spy)
    result = _tool_functions()["expand_definition"]("spy-path.py", 1, 2)
    assert opened_paths == ["spy-path.py"]
    assert result == "alpha\nbeta\n"


def test_cosk_find_usage_behavior_unchanged_with_middleware_present() -> None:
    nodes = [
        SkeletonNode(file_path="callee.py", start_line=1, end_line=1, raw_signature="def foo():", docstring=""),
        SkeletonNode(file_path="caller.py", start_line=5, end_line=5, raw_signature="def bar(x=foo()):", docstring=""),
    ]
    state.set_graph(build_graph(nodes))
    result = json.loads(_tool_functions()["find_usage"]("foo"))
    assert result and result[0]["file_path"] == "caller.py"
