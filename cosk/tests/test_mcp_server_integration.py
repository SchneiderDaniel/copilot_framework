from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from unittest.mock import Mock

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
import networkx as nx
import pytest

from cosk.extraction.parser import extract_skeleton_nodes
from cosk.graph import state
from cosk.graph.builder import RelationshipGraph
from cosk.indexing.vector_store import SkeletonNodeVectorStore
from cosk.mcp.server import create_mcp_server
from cosk.safety import middleware

pytestmark = pytest.mark.integration

FAKE_PROVIDER_FACTORY = "cosk.tests.test_mcp_server_integration:make_fake_provider"
REPO_ROOT = Path(__file__).resolve().parents[2]


class DeterministicFakeEmbeddingProvider:
    def __init__(self, dim: int = 8) -> None:
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[index] / 255.0 for index in range(self._dim)]


def make_fake_provider() -> DeterministicFakeEmbeddingProvider:
    return DeterministicFakeEmbeddingProvider()


def _server_env() -> dict[str, str]:
    env = os.environ.copy()
    env["COSK_EMBEDDING_PROVIDER_FACTORY"] = FAKE_PROVIDER_FACTORY
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) if not current_pythonpath else f"{REPO_ROOT}{os.pathsep}{current_pythonpath}"
    )
    return env


@pytest.fixture
def sample_target_dir(tmp_path: Path) -> Path:
    target = tmp_path / "sample"
    target.mkdir()
    (target / "auth.py").write_text(
        "def authenticate_user(username: str, password: str) -> bool:\n"
        "    \"\"\"Authenticate a user against local credentials.\"\"\"\n"
        "    return bool(username and password)\n",
        encoding="utf-8",
    )
    return target


@pytest.fixture
def prebuilt_index_dir(tmp_path: Path, sample_target_dir: Path) -> Path:
    db_dir = tmp_path / "prebuilt.lancedb"
    store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=make_fake_provider())
    store.rebuild_index(extract_skeleton_nodes(sample_target_dir))
    return db_dir


@pytest.fixture
def empty_valid_index_dir(tmp_path: Path) -> Path:
    db_dir = tmp_path / "empty.lancedb"
    store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=make_fake_provider())
    store.rebuild_index([])
    return db_dir


def _run_mcp_session(
    args: list[str], session_callback: Any, *, env: dict[str, str] | None = None
) -> Any:
    async def _runner() -> Any:
        server_env = _server_env()
        if env:
            server_env.update(env)
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "cosk.mcp.server", *args],
            env=server_env,
            cwd=REPO_ROOT,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await session_callback(session)

    return anyio.run(_runner)


def _tool_text_payload(result: Any) -> str:
    assert result.content
    return result.content[0].text


class _Session:
    pass


class _Context:
    def __init__(self, session: _Session) -> None:
        self.session = session


@pytest.fixture
def tool_functions() -> dict[str, Any]:
    middleware._registry.clear()  # noqa: SLF001
    state.clear_graph()
    store = Mock()
    store.search.return_value = []
    mcp = create_mcp_server(store)
    return {
        "semantic_search": mcp._tool_manager.get_tool("cosk_semantic_search").fn,  # noqa: SLF001
        "get_neighbors": mcp._tool_manager.get_tool("cosk_get_neighbors").fn,  # noqa: SLF001
        "get_symbol_source": mcp._tool_manager.get_tool("cosk_get_symbol_source").fn,  # noqa: SLF001
        "find_usage": mcp._tool_manager.get_tool("cosk_find_usage").fn,  # noqa: SLF001
        "store": store,
    }


def _set_graph(*edges: tuple[str, str]) -> None:
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    state.set_graph(RelationshipGraph(graph=graph))


def test_mcp_server_starts_with_existing_index_and_serves_stdio(prebuilt_index_dir: Path) -> None:
    tools = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], lambda session: session.list_tools())
    assert any(tool.name == "cosk_semantic_search" for tool in tools.tools)


def test_mcp_server_builds_index_when_target_dir_provided(sample_target_dir: Path, tmp_path: Path) -> None:
    db_dir = tmp_path / "rebuilt.lancedb"
    tools = _run_mcp_session(
        ["--target-dir", str(sample_target_dir), "--db-dir", str(db_dir)],
        lambda session: session.list_tools(),
    )
    assert any(tool.name == "cosk_semantic_search" for tool in tools.tools)


def test_mcp_server_aborts_on_bad_target_dir(tmp_path: Path) -> None:
    db_dir = tmp_path / "bad-target.lancedb"
    bad_target = tmp_path / "does-not-exist"
    completed = subprocess.run(
        [sys.executable, "-m", "cosk.mcp.server", "--target-dir", str(bad_target), "--db-dir", str(db_dir)],
        cwd=REPO_ROOT,
        env=_server_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stderr.strip()


def test_mcp_server_aborts_without_target_dir_when_index_missing(tmp_path: Path) -> None:
    db_dir = tmp_path / "missing-index.lancedb"
    completed = subprocess.run(
        [sys.executable, "-m", "cosk.mcp.server", "--db-dir", str(db_dir)],
        cwd=REPO_ROOT,
        env=_server_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stderr.strip()


def test_tools_list_contains_cosk_semantic_search(prebuilt_index_dir: Path) -> None:
    tools = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], lambda session: session.list_tools())
    assert any(tool.name == "cosk_semantic_search" for tool in tools.tools)


def test_tools_list_contains_all_tools(prebuilt_index_dir: Path) -> None:
    tools = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], lambda session: session.list_tools())
    names = {tool.name for tool in tools.tools}
    assert {"cosk_semantic_search", "cosk_get_neighbors", "cosk_get_symbol_source", "cosk_find_usage"} <= names
    assert "cosk_expand_definition" not in names


def test_cosk_semantic_search_happy_path_returns_required_json_fields(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_semantic_search", {"query_string": "user authentication"})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    payload = json.loads(_tool_text_payload(result))
    assert isinstance(payload, list)
    assert len(payload) <= 5
    if payload:
        assert {"node_id", "file_path", "start_line", "end_line", "raw_signature", "summary"} <= set(payload[0])
        assert "graph_node_id" in payload[0]
        assert "token_count" in payload[0]


def test_cosk_semantic_search_blank_query_returns_mcp_error(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_semantic_search", {"query_string": "   "})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True


def test_cosk_get_neighbors_works_when_graph_rebuilt_from_loaded_index(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_get_neighbors", {"node_id": "module.py:1"})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is False
    payload = json.loads(_tool_text_payload(result))
    assert set(payload) == {"inbound", "outbound"}


def test_cosk_get_neighbors_blank_node_id_returns_mcp_error(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_get_neighbors", {"node_id": "   "})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True


def test_cosk_find_usage_works_when_graph_rebuilt_from_loaded_index(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_find_usage", {"entity_name": "foo"})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is False
    assert isinstance(json.loads(_tool_text_payload(result)), list)


def test_cosk_find_usage_blank_entity_name_returns_mcp_error(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_find_usage", {"entity_name": "   "})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True


def test_cosk_semantic_search_empty_index_returns_empty_array(empty_valid_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_semantic_search", {"query_string": "find auth"})

    result = _run_mcp_session(["--db-dir", str(empty_valid_index_dir)], _call)
    assert json.loads(_tool_text_payload(result)) == []


def test_index_search_get_symbol_source_round_trip_returns_exact_lines(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> tuple[Any, Any]:
        search = await session.call_tool("cosk_semantic_search", {"query_string": "authenticate user"})
        search_payload = json.loads(_tool_text_payload(search))
        symbol = await session.call_tool("cosk_get_symbol_source", {"node_ids": [search_payload[0]["node_id"]]})
        return search, symbol

    search_result, symbol_result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert not search_result.isError
    assert not symbol_result.isError
    search_payload = json.loads(_tool_text_payload(search_result))
    symbol_payload = json.loads(_tool_text_payload(symbol_result))
    assert len(symbol_payload) == 1
    entry = symbol_payload[0]
    assert entry["node_id"] == search_payload[0]["node_id"]
    expected_lines = Path(entry["file_path"]).read_text(encoding="utf-8").splitlines(keepends=True)
    assert entry["source_code"] == "".join(expected_lines[entry["start_line"] - 1 : entry["end_line"]])
    assert "token_count" in entry


def test_cosk_get_symbol_source_mixed_valid_invalid_batch(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        search = await session.call_tool("cosk_semantic_search", {"query_string": "authenticate"})
        search_payload = json.loads(_tool_text_payload(search))
        return await session.call_tool(
            "cosk_get_symbol_source",
            {"node_ids": [search_payload[0]["node_id"], "missing-node-id"]},
        )

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert not result.isError
    payload = json.loads(_tool_text_payload(result))
    assert payload[0]["node_id"]
    assert payload[1] == {"node_id": "missing-node-id", "error": "not found"}


def test_get_symbol_source_empty_node_ids_returns_mcp_error(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_get_symbol_source", {"node_ids": []})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True


def test_e2e_agent_flow_initialize_list_tools_call_search(prebuilt_index_dir: Path) -> None:
    async def _flow(session: ClientSession) -> tuple[Any, Any]:
        tools = await session.list_tools()
        search_result = await session.call_tool("cosk_semantic_search", {"query_string": "authenticate"})
        return tools, search_result

    tools, search_result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _flow)
    assert any(tool.name == "cosk_semantic_search" for tool in tools.tools)
    assert isinstance(json.loads(_tool_text_payload(search_result)), list)


def test_safety_middleware_applies_only_to_get_neighbors(tool_functions: dict[str, Any], tmp_path: Path) -> None:
    _set_graph(("a.py:1", "a.py:2"))
    ctx = _Context(_Session())
    source_file = tmp_path / "sample.py"
    source_file.write_text("a\nb\n", encoding="utf-8")
    tool_functions["store"].search.return_value = [{"node_id": "hash", "file_path": "a.py", "start_line": 1}]
    tool_functions["store"].get_node_details.return_value = {
        "id1": {"file_path": str(source_file), "start_line": 1, "end_line": 1, "raw_signature": "def a():"}
    }

    assert json.loads(tool_functions["semantic_search"]("query", ctx=ctx))
    assert json.loads(tool_functions["get_symbol_source"](["id1"], ctx=ctx))[0]["source_code"] == "a\n"
    assert tool_functions["find_usage"]("foo") == "[]"
    assert json.loads(tool_functions["get_neighbors"]("a.py:1", ctx=ctx))
    assert tool_functions["get_neighbors"]("a.py:1", ctx=ctx) == middleware.REVISIT_NOTICE


def test_end_to_end_revisit_soft_block(tool_functions: dict[str, Any]) -> None:
    _set_graph(("a.py:1", "a.py:2"))
    ctx = _Context(_Session())
    assert json.loads(tool_functions["get_neighbors"]("a.py:1", ctx=ctx))
    assert tool_functions["get_neighbors"]("a.py:1", ctx=ctx) == middleware.REVISIT_NOTICE


def test_end_to_end_depth_soft_block(tool_functions: dict[str, Any]) -> None:
    _set_graph(("a.py:1", "a.py:2"), ("a.py:2", "a.py:3"), ("a.py:3", "a.py:4"), ("a.py:4", "a.py:5"))
    ctx = _Context(_Session())
    tool_functions["store"].search.return_value = [{"node_id": "hash", "file_path": "a.py", "start_line": 1}]
    tool_functions["semantic_search"]("query", ctx=ctx)
    assert tool_functions["get_neighbors"]("a.py:5", ctx=ctx) == middleware.DEPTH_NOTICE


def test_get_symbol_source_unlocks_depth_limit(tool_functions: dict[str, Any], tmp_path: Path) -> None:
    _set_graph(("a.py:1", "a.py:2"), ("a.py:2", "a.py:3"), ("a.py:3", "a.py:4"), ("a.py:4", "a.py:5"))
    ctx = _Context(_Session())
    tool_functions["store"].search.return_value = [{"node_id": "hash", "file_path": "a.py", "start_line": 1}]
    tool_functions["semantic_search"]("query", ctx=ctx)
    source_file = tmp_path / "sample.py"
    source_file.write_text("a\n", encoding="utf-8")
    tool_functions["store"].get_node_details.return_value = {
        "id1": {"file_path": str(source_file), "start_line": 1, "end_line": 1, "raw_signature": "def a():"}
    }
    json.loads(tool_functions["get_symbol_source"](["id1"], ctx=ctx))
    assert json.loads(tool_functions["get_neighbors"]("a.py:5", ctx=ctx))


def test_origin_does_not_reset_after_second_search(tool_functions: dict[str, Any]) -> None:
    _set_graph(
        ("origin.py:1", "a.py:2"),
        ("a.py:2", "a.py:3"),
        ("a.py:3", "a.py:4"),
        ("a.py:4", "a.py:5"),
        ("later.py:1", "a.py:5"),
    )
    ctx = _Context(_Session())
    tool_functions["store"].search.return_value = [{"node_id": "hash1", "file_path": "origin.py", "start_line": 1}]
    tool_functions["semantic_search"]("first", ctx=ctx)
    tool_functions["store"].search.return_value = [{"node_id": "hash2", "file_path": "later.py", "start_line": 1}]
    tool_functions["semantic_search"]("second", ctx=ctx)
    assert tool_functions["get_neighbors"]("a.py:5", ctx=ctx) == middleware.DEPTH_NOTICE


def test_session_disconnect_resets_state(tool_functions: dict[str, Any]) -> None:
    _set_graph(("a.py:1", "a.py:2"))
    ctx1 = _Context(_Session())
    assert json.loads(tool_functions["get_neighbors"]("a.py:1", ctx=ctx1))
    assert tool_functions["get_neighbors"]("a.py:1", ctx=ctx1) == middleware.REVISIT_NOTICE

    ctx2 = _Context(_Session())
    assert json.loads(tool_functions["get_neighbors"]("a.py:1", ctx=ctx2))


def test_per_client_isolation(tool_functions: dict[str, Any]) -> None:
    _set_graph(("a.py:1", "a.py:2"))
    ctx1 = _Context(_Session())
    ctx2 = _Context(_Session())
    assert json.loads(tool_functions["get_neighbors"]("a.py:1", ctx=ctx1))
    assert json.loads(tool_functions["get_neighbors"]("a.py:1", ctx=ctx2))
    assert tool_functions["get_neighbors"]("a.py:1", ctx=ctx1) == middleware.REVISIT_NOTICE
    assert tool_functions["get_neighbors"]("a.py:1", ctx=ctx2) == middleware.REVISIT_NOTICE
