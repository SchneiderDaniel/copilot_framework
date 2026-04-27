from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

from cosk.config import get_cosk_config
from cosk.http_server import create_http_app, run_http_server
from cosk.index_service import IndexSyncResult


class _Store:
    def search(self, query: str, top_k: int):  # noqa: ARG002
        return [{"node_id": "n1", "file_path": "a.py", "start_line": 1, "end_line": 1, "raw_signature": "def a()", "summary": ""}]

    def get_node_details(self, node_ids):  # noqa: ANN001
        return {node_id: {"raw_signature": "", "summary": ""} for node_id in node_ids}


class _Graph:
    def get_neighbors(self, node_id: str):  # noqa: ARG002
        return {"inbound": [], "outbound": []}

    def find_usages(self, entity_name: str):  # noqa: ARG002
        return []


@dataclass
class _Context:
    vector_store: object
    graph: object
    target_dir: Path


class _Manager:
    def __init__(self) -> None:
        self.config = get_cosk_config()

    def get_context(self, index_name=None, db_dir=None):  # noqa: ANN001, ARG002
        return _Context(vector_store=_Store(), graph=_Graph(), target_dir=Path.cwd())

    def sync(self, request):  # noqa: ANN001
        return IndexSyncResult(
            mode="full",
            index_name=request.name or "default",
            target_dir=str(request.target_dir),
            db_dir=str(request.db_dir or (request.target_dir / ".lancedb")),
            added_files=1,
            updated_files=0,
            deleted_files=0,
            indexed_nodes=1,
        )

    def list_registry(self) -> dict[str, object]:
        return {"version": 1, "default": "default", "indexes": {}}


def _create_app_or_skip(manager: object):
    try:
        return create_http_app(manager)
    except TypeError as exc:
        if "on_startup" in str(exc):
            pytest.skip("FastAPI/Starlette versions are incompatible in this environment")
        raise


def test_create_http_app_has_no_side_effects() -> None:
    class _NoCallManager(_Manager):
        def get_context(self, index_name=None, db_dir=None):  # noqa: ANN001, ARG002
            raise AssertionError("Should not be called during app creation")

    app = _create_app_or_skip(_NoCallManager())
    paths = {route.path for route in app.routes}
    assert "/v1/search" in paths
    assert "/v1/events/index" in paths


def test_missing_optional_deps_raise_clear_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "fastapi", None)
    with pytest.raises(RuntimeError, match="FastAPI is required"):
        create_http_app(_Manager())

    monkeypatch.setitem(sys.modules, "uvicorn", None)
    with pytest.raises(RuntimeError, match="uvicorn is required"):
        run_http_server(_Manager(), "127.0.0.1", 9999)


def test_http_json_endpoints_exist_and_return_json() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    client = TestClient(_create_app_or_skip(_Manager()))
    assert client.post("/v1/search", json={"query_string": "a"}).status_code == 200
    assert client.post("/v1/neighbors", json={"node_id": "a.py:1"}).status_code == 200
    assert client.post("/v1/expand", json={"file_path": __file__, "start_line": 1, "end_line": 1}).status_code == 200
    assert client.post("/v1/find-usage", json={"entity_name": "foo"}).status_code == 200
    assert client.post("/v1/index", json={"target_dir": str(Path.cwd())}).status_code == 200
    assert client.get("/v1/registry").status_code == 200


def test_default_http_bind_config_values() -> None:
    config = get_cosk_config()
    assert config.transport.http_host == "127.0.0.1"
    assert isinstance(config.transport.http_port, int)
