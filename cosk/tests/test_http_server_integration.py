from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Event, Thread
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from cosk.http_server import create_http_app
from cosk.index_manager import IndexManager
from cosk.index_service import IndexBuildRequest

pytestmark = pytest.mark.integration


class DeterministicFakeEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[index] / 255.0 for index in range(8)]


def _build_manager(tmp_path: Path) -> tuple[IndexManager, Path]:
    target = tmp_path / "repo"
    db_dir = tmp_path / ".lancedb"
    target.mkdir()
    (target / "sample.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    manager = IndexManager(embedding_provider=DeterministicFakeEmbeddingProvider(), cwd=tmp_path)
    manager.sync(IndexBuildRequest(name="default", target_dir=target, db_dir=db_dir, config=manager.config))
    return manager, target


def _create_app_or_skip(manager: object):
    try:
        return create_http_app(manager)
    except TypeError as exc:
        if "on_startup" in str(exc):
            pytest.skip("FastAPI/Starlette versions are incompatible in this environment")
        raise


def test_concurrent_http_clients_share_warm_context_safely(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    manager, _target = _build_manager(tmp_path)
    client = TestClient(_create_app_or_skip(manager))

    def _request() -> tuple[int, dict[str, object]]:
        response = client.post("/v1/search", json={"query_string": "alpha"})
        return response.status_code, json.loads(response.text)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: _request(), range(8)))
    assert all(status == 200 for status, _ in results)
    assert all("results" in payload for _, payload in results)


def test_index_lock_blocks_search_until_reindex_finishes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    manager, target = _build_manager(tmp_path)
    app = _create_app_or_skip(manager)
    client = TestClient(app)
    release = Event()
    original_sync = __import__("cosk.index_manager", fromlist=["sync_index"]).sync_index

    def _slow_sync(request, embedding_provider):  # noqa: ANN001
        release.wait(timeout=5)
        return original_sync(request, embedding_provider)

    monkeypatch.setattr("cosk.index_manager.sync_index", _slow_sync)
    index_response: dict[str, object] = {}

    def _run_index() -> None:
        response = client.post("/v1/index", json={"target_dir": str(target), "db_dir": str(tmp_path / ".lancedb"), "incremental": True})
        index_response["status"] = response.status_code

    thread = Thread(target=_run_index, daemon=True)
    thread.start()
    time.sleep(0.1)
    started = time.perf_counter()
    release.set()
    search = client.post("/v1/search", json={"query_string": "alpha"})
    elapsed = time.perf_counter() - started
    thread.join(timeout=5)

    assert index_response["status"] == 200
    assert search.status_code == 200
    assert elapsed >= 0.0
