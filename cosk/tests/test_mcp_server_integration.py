from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
import pytest

from cosk.extraction.parser import extract_skeleton_nodes
from cosk.indexing.vector_store import SkeletonNodeVectorStore

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
    assert {"cosk_semantic_search", "cosk_get_neighbors", "cosk_expand_definition", "cosk_find_usage"} <= names


def test_cosk_semantic_search_happy_path_returns_required_json_fields(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_semantic_search", {"query_string": "user authentication"})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    payload = json.loads(_tool_text_payload(result))
    assert isinstance(payload, list)
    assert len(payload) <= 5
    if payload:
        assert set(payload[0]) == {"node_id", "file_path", "start_line", "end_line", "raw_signature", "summary"}


def test_cosk_semantic_search_blank_query_returns_mcp_error(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_semantic_search", {"query_string": "   "})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True


def test_cosk_get_neighbors_returns_is_error_true_when_graph_not_loaded(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_get_neighbors", {"node_id": "module.py:1"})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True
    assert "relationship graph is not loaded" in _tool_text_payload(result)


def test_cosk_get_neighbors_blank_node_id_returns_mcp_error(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_get_neighbors", {"node_id": "   "})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True


def test_cosk_find_usage_returns_is_error_true_when_graph_not_loaded(prebuilt_index_dir: Path) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_find_usage", {"entity_name": "foo"})

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert result.isError is True
    assert "relationship graph is not loaded" in _tool_text_payload(result)


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


def test_cosk_expand_definition_happy_path_returns_inclusive_text_payload(prebuilt_index_dir: Path, tmp_path: Path) -> None:
    source_file = tmp_path / "sample.py"
    lines = ["one\n", "two\n", "three\n", "four\n"]
    source_file.write_text("".join(lines), encoding="utf-8")

    async def _call(session: ClientSession) -> Any:
        return await session.call_tool(
            "cosk_expand_definition",
            {"file_path": str(source_file), "start_line": 2, "end_line": 3},
        )

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert not result.isError
    assert _tool_text_payload(result) == "".join(lines[1:3])


def test_cosk_expand_definition_missing_file_returns_text_not_tool_error(
    prebuilt_index_dir: Path, tmp_path: Path
) -> None:
    missing_file = tmp_path / "missing.py"

    async def _call(session: ClientSession) -> Any:
        return await session.call_tool(
            "cosk_expand_definition",
            {"file_path": str(missing_file), "start_line": 1, "end_line": 2},
        )

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert not result.isError
    payload = _tool_text_payload(result)
    assert isinstance(payload, str)
    assert str(missing_file) in payload


def test_cosk_expand_definition_out_of_range_returns_descriptive_text_not_tool_error(
    prebuilt_index_dir: Path, tmp_path: Path
) -> None:
    source_file = tmp_path / "sample.py"
    source_file.write_text("a\nb\n", encoding="utf-8")

    async def _call(session: ClientSession) -> Any:
        return await session.call_tool(
            "cosk_expand_definition",
            {"file_path": str(source_file), "start_line": 2, "end_line": 4},
        )

    result = _run_mcp_session(["--db-dir", str(prebuilt_index_dir)], _call)
    assert not result.isError
    assert "Requested line range 2-4 is outside file bounds; file has 2 lines." in _tool_text_payload(result)


@pytest.mark.parametrize(
    "payload",
    [
        {"file_path": "file.py", "start_line": 0, "end_line": 1},
        {"file_path": "file.py", "start_line": 3, "end_line": 2},
        {"file_path": "   ", "start_line": 1, "end_line": 1},
    ],
)
def test_cosk_expand_definition_invalid_params_return_mcp_error(prebuilt_index_dir: Path, payload: dict[str, object]) -> None:
    async def _call(session: ClientSession) -> Any:
        return await session.call_tool("cosk_expand_definition", payload)

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
