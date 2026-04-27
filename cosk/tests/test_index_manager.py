from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
import time

from cosk.index_manager import IndexManager
from cosk.index_service import IndexBuildRequest, IndexSyncResult


class _FakeVectorStore:
    created = 0

    def __init__(self, *, db_dir: Path, embedding_provider: object):  # noqa: ARG002
        type(self).created += 1
        self.db_dir = db_dir

    def validate_index(self) -> bool:
        return True

    def load_all_nodes(self) -> list[object]:
        return []


@dataclass
class _Entry:
    target_dir: str
    db_dir: str


def test_get_context_resolves_by_index_name(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    db_dir = tmp_path / "alpha.lancedb"
    target.mkdir()
    monkeypatch.setattr("cosk.index_manager.resolve_index", lambda name, cwd: ("alpha", _Entry(str(target), str(db_dir))))
    monkeypatch.setattr("cosk.index_manager.SkeletonNodeVectorStore", _FakeVectorStore)
    monkeypatch.setattr("cosk.index_manager.rebuild", lambda nodes: {"count": len(nodes)})
    monkeypatch.setattr("cosk.index_manager.load_manifest", lambda _: None)
    manager = IndexManager(embedding_provider=object(), cwd=tmp_path)
    context = manager.get_context(index_name="alpha")
    assert context.name == "alpha"
    assert context.target_dir == target
    assert context.db_dir == db_dir


def test_get_context_uses_warm_cache(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    db_dir = tmp_path / "cache.lancedb"
    target.mkdir()
    _FakeVectorStore.created = 0
    monkeypatch.setattr("cosk.index_manager.resolve_index", lambda name, cwd: ("default", _Entry(str(target), str(db_dir))))
    monkeypatch.setattr("cosk.index_manager.SkeletonNodeVectorStore", _FakeVectorStore)
    monkeypatch.setattr("cosk.index_manager.rebuild", lambda nodes: nodes)
    monkeypatch.setattr("cosk.index_manager.load_manifest", lambda _: None)
    manager = IndexManager(embedding_provider=object(), cwd=tmp_path)
    context_a = manager.get_context(index_name="default")
    context_b = manager.get_context(index_name="default")
    assert context_a is context_b
    assert _FakeVectorStore.created == 1


def test_sync_uses_per_index_lock_for_concurrent_calls(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    manager = IndexManager(embedding_provider=object(), cwd=tmp_path)
    active = {"count": 0, "max": 0}
    active_lock = Lock()

    def _slow_sync(request, embedding_provider):  # noqa: ANN001, ARG001
        with active_lock:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
        time.sleep(0.05)
        with active_lock:
            active["count"] -= 1
        return IndexSyncResult(
            mode="incremental",
            index_name=request.name or "default",
            target_dir=str(request.target_dir),
            db_dir=str(request.db_dir or (request.target_dir / ".lancedb")),
            added_files=0,
            updated_files=0,
            deleted_files=0,
            indexed_nodes=0,
        )

    monkeypatch.setattr("cosk.index_manager.sync_index", _slow_sync)
    request = IndexBuildRequest(name="default", target_dir=target, db_dir=tmp_path / ".lancedb")

    threads = [Thread(target=lambda: manager.sync(request)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert active["max"] == 1
