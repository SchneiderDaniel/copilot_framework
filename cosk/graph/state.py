from __future__ import annotations

from threading import Lock

_STATE_LOCK: Lock = Lock()
_GRAPH = None  # RelationshipGraph | None


def get_graph():
    with _STATE_LOCK:
        return _GRAPH


def set_graph(graph) -> None:
    global _GRAPH
    with _STATE_LOCK:
        _GRAPH = graph


def clear_graph() -> None:
    global _GRAPH
    with _STATE_LOCK:
        _GRAPH = None
