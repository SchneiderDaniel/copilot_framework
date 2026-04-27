from __future__ import annotations

import json
from pathlib import Path
import threading
import types

import pytest

from cosk.index_service import IndexSyncResult
from cosk.watch_mode import run_watch_loop

pytestmark = pytest.mark.integration


class _Manager:
    config = object()

    def __init__(self) -> None:
        self.calls = 0
        self.max_concurrent = 0
        self._active = 0
        self._lock = threading.Lock()

    def sync(self, request):  # noqa: ANN001
        with self._lock:
            self._active += 1
            self.max_concurrent = max(self.max_concurrent, self._active)
        self.calls += 1
        with self._lock:
            self._active -= 1
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


class _Observer:
    def __init__(self, callback) -> None:  # noqa: ANN001
        self._handler = None
        self._callback = callback

    def schedule(self, handler, path: str, recursive: bool):  # noqa: ANN001, ARG002
        self._handler = handler

    def start(self) -> None:
        self._callback(self._handler)

    def stop(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:  # noqa: ARG002
        return None


def _install_watchdog(monkeypatch: pytest.MonkeyPatch, observer: _Observer) -> None:
    import sys

    events_module = types.ModuleType("watchdog.events")
    events_module.FileSystemEventHandler = object
    observers_module = types.ModuleType("watchdog.observers")
    observers_module.Observer = lambda: observer
    monkeypatch.setitem(sys.modules, "watchdog", types.ModuleType("watchdog"))
    monkeypatch.setitem(sys.modules, "watchdog.events", events_module)
    monkeypatch.setitem(sys.modules, "watchdog.observers", observers_module)


def test_watch_loop_emits_jsonl_sequence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    observer = _Observer(lambda handler: handler.on_any_event(types.SimpleNamespace(is_directory=False, event_type="modified")))
    _install_watchdog(monkeypatch, observer)
    calls = {"sleep": 0}

    def _sleep(_: float) -> None:
        calls["sleep"] += 1
        if calls["sleep"] >= 1:
            raise KeyboardInterrupt

    monkeypatch.setattr("cosk.watch_mode.time.sleep", _sleep)
    manager = _Manager()
    emitted: list[str] = []
    run_watch_loop(manager=manager, target_dir=target, debounce_seconds=0.0, emit=emitted.append)
    events = [json.loads(line)["event"] for line in emitted]
    assert events == ["started", "change_detected", "reindex_completed"]


def test_rapid_events_do_not_create_overlapping_index_ops(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()

    def _burst(handler) -> None:  # noqa: ANN001
        for _ in range(10):
            handler.on_any_event(types.SimpleNamespace(is_directory=False, event_type="modified"))

    _install_watchdog(monkeypatch, _Observer(_burst))
    monkeypatch.setattr("cosk.watch_mode.time.sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))
    manager = _Manager()
    run_watch_loop(manager=manager, target_dir=target, debounce_seconds=0.0, emit=lambda _: None)
    assert manager.calls == 1
    assert manager.max_concurrent == 1
