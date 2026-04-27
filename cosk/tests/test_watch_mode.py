from __future__ import annotations

import json
from pathlib import Path
import types

import pytest

from cosk.index_service import IndexSyncResult
from cosk.watch_mode import run_watch_loop


class _Manager:
    config = object()

    def __init__(self) -> None:
        self.requests: list[object] = []

    def sync(self, request):  # noqa: ANN001
        self.requests.append(request)
        return IndexSyncResult(
            mode="incremental",
            index_name="default",
            target_dir=str(request.target_dir),
            db_dir=str(request.db_dir or (request.target_dir / ".lancedb")),
            added_files=0,
            updated_files=0,
            deleted_files=0,
            indexed_nodes=0,
        )


class _FakeObserver:
    def __init__(self, start_callback=None) -> None:
        self._handler = None
        self.start_callback = start_callback
        self.stopped = False
        self.joined = False

    def schedule(self, handler, path: str, recursive: bool):  # noqa: ANN001, ARG002
        self._handler = handler

    def start(self) -> None:
        if self.start_callback is not None:
            self.start_callback(self._handler)

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:  # noqa: ARG002
        self.joined = True


def _install_fake_watchdog(monkeypatch: pytest.MonkeyPatch, observer: _FakeObserver) -> None:
    events_module = types.ModuleType("watchdog.events")
    events_module.FileSystemEventHandler = object
    observers_module = types.ModuleType("watchdog.observers")
    observers_module.Observer = lambda: observer
    monkeypatch.setitem(__import__("sys").modules, "watchdog", types.ModuleType("watchdog"))
    monkeypatch.setitem(__import__("sys").modules, "watchdog.events", events_module)
    monkeypatch.setitem(__import__("sys").modules, "watchdog.observers", observers_module)


def test_watch_mode_errors_for_missing_target_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_watch_loop(manager=_Manager(), target_dir=tmp_path / "missing")


def test_watch_mode_debounce_coalesces_burst_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.mkdir()
    burst_observer = _FakeObserver(
        start_callback=lambda handler: [
            handler.on_any_event(types.SimpleNamespace(is_directory=False, event_type="created")),
            handler.on_any_event(types.SimpleNamespace(is_directory=False, event_type="modified")),
            handler.on_any_event(types.SimpleNamespace(is_directory=False, event_type="deleted")),
        ]
    )
    _install_fake_watchdog(monkeypatch, burst_observer)
    sleep_calls = {"count": 0}

    def _sleep(_: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 1:
            raise KeyboardInterrupt

    monkeypatch.setattr("cosk.watch_mode.time.sleep", _sleep)
    manager = _Manager()
    events: list[str] = []
    exit_code = run_watch_loop(manager=manager, target_dir=target, debounce_seconds=0.0, emit=events.append)
    assert exit_code == 0
    assert len(manager.requests) == 1
    parsed = [json.loads(event)["event"] for event in events]
    assert parsed == ["started", "change_detected", "reindex_completed"]


def test_watch_mode_change_events_trigger_incremental_sync(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.mkdir()
    observer = _FakeObserver(
        start_callback=lambda handler: [
            handler.on_any_event(types.SimpleNamespace(is_directory=False, event_type=kind))
            for kind in ("created", "modified", "deleted", "moved")
        ]
    )
    _install_fake_watchdog(monkeypatch, observer)
    monkeypatch.setattr("cosk.watch_mode.time.sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))
    manager = _Manager()
    run_watch_loop(manager=manager, target_dir=target, debounce_seconds=0.0, emit=lambda _: None)
    assert len(manager.requests) == 1
    assert manager.requests[0].incremental is True


def test_watch_mode_stops_cleanly_on_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.mkdir()
    observer = _FakeObserver()
    _install_fake_watchdog(monkeypatch, observer)
    monkeypatch.setattr("cosk.watch_mode.time.sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))
    code = run_watch_loop(manager=_Manager(), target_dir=target, debounce_seconds=1.0, emit=lambda _: None)
    assert code == 0
    assert observer.stopped is True
    assert observer.joined is True
