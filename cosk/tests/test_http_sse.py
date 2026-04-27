from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

import pytest

from cosk.http_server import create_http_app
from cosk.index_service import IndexSyncResult


class _Store:
    def search(self, query: str, top_k: int):  # noqa: ARG002
        return [
            {"node_id": "a", "file_path": "a.py", "start_line": 1, "end_line": 2, "raw_signature": "def a()", "summary": ""},
            {"node_id": "b", "file_path": "b.py", "start_line": 3, "end_line": 4, "raw_signature": "def b()", "summary": ""},
        ]


class _Context:
    vector_store = _Store()
    graph = type("_Graph", (), {"get_neighbors": lambda self, node_id: {"inbound": [], "outbound": []}, "find_usages": lambda self, entity_name: []})()  # noqa: E731
    target_dir = Path.cwd()


class _Manager:
    config = type("_Config", (), {"retrieval": type("_R", (), {"default_top_k": 5, "max_top_k": 20})(), "transport": type("_T", (), {"http_host": "127.0.0.1", "http_port": 8765})()})()

    def __init__(self, *, fail_sync: bool = False) -> None:
        self.fail_sync = fail_sync
        self.lock = Lock()

    def get_context(self, index_name=None, db_dir=None):  # noqa: ANN001, ARG002
        return _Context()

    def list_registry(self) -> dict[str, object]:
        return {"version": 1, "default": "default", "indexes": {}}

    def sync(self, request):  # noqa: ANN001
        with self.lock:
            if self.fail_sync:
                raise RuntimeError("boom")
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


def _create_app_or_skip(manager: object):
    try:
        return create_http_app(manager)
    except TypeError as exc:
        if "on_startup" in str(exc):
            pytest.skip("FastAPI/Starlette versions are incompatible in this environment")
        raise


def _parse_events(payload: str) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for block in [chunk for chunk in payload.split("\n\n") if chunk.strip()]:
        event_name = ""
        event_data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.replace("event: ", "", 1)
            if line.startswith("data: "):
                event_data = line.replace("data: ", "", 1)
        if event_name:
            parsed.append((event_name, event_data))
    return parsed


def test_search_sse_sequence_meta_result_done() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    client = TestClient(_create_app_or_skip(_Manager()))
    response = client.get("/v1/events/search", params={"query_string": "a"})
    assert response.status_code == 200
    names = [name for name, _ in _parse_events(response.text)]
    assert names[0] == "meta"
    assert names[-1] == "done"
    assert names.count("result") >= 1


def test_index_sse_emits_error_event_on_sync_failure() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    client = TestClient(_create_app_or_skip(_Manager(fail_sync=True)))
    response = client.get("/v1/events/index", params={"target_dir": str(Path.cwd())})
    assert response.status_code == 200
    events = _parse_events(response.text)
    names = [name for name, _ in events]
    assert names == ["started", "error"]
    assert json.loads(events[1][1])["message"] == "boom"


def test_index_sse_client_disconnect_does_not_leak_lock() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    manager = _Manager()
    client = TestClient(_create_app_or_skip(manager))
    with client.stream("GET", "/v1/events/index", params={"target_dir": str(Path.cwd())}) as stream:
        next(stream.iter_text())
    assert manager.lock.locked() is False
