from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from threading import Event, Lock

from cosk.index_manager import IndexManager
from cosk.index_service import IndexBuildRequest


class _ChangeState:
    def __init__(self) -> None:
        self._dirty = False
        self._last_change_at = 0.0
        self._lock = Lock()

    def mark_dirty(self) -> None:
        with self._lock:
            self._dirty = True
            self._last_change_at = time.monotonic()

    def consume_if_debounced(self, debounce_seconds: float) -> bool:
        with self._lock:
            if not self._dirty:
                return False
            if time.monotonic() - self._last_change_at < debounce_seconds:
                return False
            self._dirty = False
            return True


def run_watch_loop(
    *,
    manager: IndexManager,
    target_dir: Path,
    db_dir: Path | None = None,
    name: str | None = None,
    debounce_seconds: float = 0.8,
    emit: callable = print,
) -> int:
    if not target_dir.exists() or not target_dir.is_dir():
        raise ValueError(f"Target directory does not exist or is not a directory: '{target_dir}'.")
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("watchdog is required for watch mode. Install with: pip install 'cosk[watch]'") from exc

    state = _ChangeState()
    stop_event = Event()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):  # noqa: ANN001
            if getattr(event, "is_directory", False):
                return
            state.mark_dirty()

    observer = Observer()
    observer.schedule(Handler(), str(target_dir), recursive=True)
    observer.start()
    emit(json.dumps({"event": "started", "target_dir": target_dir.resolve().as_posix()}))
    try:
        while not stop_event.is_set():
            if state.consume_if_debounced(debounce_seconds):
                emit(json.dumps({"event": "change_detected"}))
                result = manager.sync(
                    IndexBuildRequest(
                        name=name,
                        target_dir=target_dir,
                        db_dir=db_dir,
                        incremental=True,
                        config=manager.config,
                    )
                )
                emit(json.dumps({"event": "reindex_completed", "result": dataclasses.asdict(result)}))
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join(timeout=2)
    return 0

