from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from mcp.shared.exceptions import McpError
import pytest

from cosk.http_server import create_http_app
from cosk.index_manager import IndexManager
from cosk.index_service import IndexBuildRequest
from cosk.mcp.server import create_mcp_server

pytestmark = pytest.mark.integration

COSK_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = COSK_DIR.parent
FAKE_PROVIDER_FACTORY = "cosk.tests.test_multi_repo_integration:make_fake_provider"


class DeterministicFakeEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[index] / 255.0 for index in range(8)]


def make_fake_provider() -> DeterministicFakeEmbeddingProvider:
    return DeterministicFakeEmbeddingProvider()


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["COSK_EMBEDDING_PROVIDER_FACTORY"] = FAKE_PROVIDER_FACTORY
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _run_cli(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cosk.cli.main", *args],
        cwd=cwd,
        env=_cli_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _create_http_app_or_skip(manager: object):
    try:
        return create_http_app(manager)
    except TypeError as exc:
        if "on_startup" in str(exc):
            pytest.skip("FastAPI/Starlette versions are incompatible in this environment")
        raise


def test_multi_repo_routing_registry_and_unknown_index_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    provider = make_fake_provider()
    manager = IndexManager(embedding_provider=provider, cwd=tmp_path)
    alpha_target = tmp_path / "alpha_repo"
    beta_target = tmp_path / "beta_repo"
    alpha_target.mkdir()
    beta_target.mkdir()
    (alpha_target / "alpha.py").write_text("def alpha_symbol():\n    return 'alpha'\n", encoding="utf-8")
    (beta_target / "beta.py").write_text("def beta_symbol():\n    return 'beta'\n", encoding="utf-8")

    manager.sync(IndexBuildRequest(name="alpha", target_dir=alpha_target, db_dir=tmp_path / "alpha.lancedb", config=manager.config))
    manager.sync(IndexBuildRequest(name="beta", target_dir=beta_target, db_dir=tmp_path / "beta.lancedb", config=manager.config))

    alpha_context = manager.get_context(index_name="alpha")
    beta_context = manager.get_context(index_name="beta")
    assert alpha_context.db_dir != beta_context.db_dir
    assert alpha_context.vector_store.search("alpha_symbol", top_k=3)
    assert beta_context.vector_store.search("beta_symbol", top_k=3)

    listed = _run_cli(["registry", "list"], cwd=tmp_path)
    assert listed.returncode == 0, listed.stderr
    payload = json.loads(listed.stdout)
    assert {"alpha", "beta"} <= set(payload["indexes"])

    set_default = _run_cli(["registry", "set-default", "--name", "beta"], cwd=tmp_path)
    assert set_default.returncode == 0, set_default.stderr
    removed = _run_cli(["registry", "remove", "--name", "alpha"], cwd=tmp_path)
    assert removed.returncode == 0, removed.stderr

    cli_unknown = _run_cli(["search", "--query", "x", "--name", "unknown"], cwd=tmp_path)
    assert cli_unknown.returncode != 0
    assert cli_unknown.stderr.strip()

    mcp = create_mcp_server(manager=manager)
    semantic = mcp._tool_manager.get_tool("cosk_semantic_search").fn  # noqa: SLF001
    with pytest.raises(McpError) as mcp_error:
        semantic("alpha_symbol", index_name="unknown")
    assert str(mcp_error.value)

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    client = TestClient(_create_http_app_or_skip(manager), raise_server_exceptions=False)
    response = client.post("/v1/search", json={"query_string": "alpha_symbol", "index_name": "unknown"})
    assert response.status_code == 500
    assert response.text
