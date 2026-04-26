from __future__ import annotations

from dataclasses import dataclass, field
import os
from threading import Lock
from typing import Any, Callable
import weakref

import networkx as nx

DEFAULT_REVISIT_THRESHOLD = 1
DEFAULT_MAX_DEPTH = 3

REVISIT_NOTICE = (
    "Notice: You have already traversed this node. Please analyze your current context or use cosk_expand_definition."
)
DEPTH_NOTICE = "Notice: Depth limit reached. Summarize your findings or expand a definition."

_registry_lock = Lock()
_registry: weakref.WeakKeyDictionary[object, "SessionState"] = weakref.WeakKeyDictionary()


@dataclass(slots=True)
class SessionState:
    visit_counts: dict[str, int] = field(default_factory=dict)
    origin_node_ids: frozenset[str] | None = None
    expand_definition_used: bool = False


def _get_env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < minimum:
        return default
    return value


def get_revisit_threshold() -> int:
    return _get_env_int("COSK_REVISIT_THRESHOLD", DEFAULT_REVISIT_THRESHOLD, minimum=1)


def get_max_traversal_depth() -> int:
    return _get_env_int("COSK_MAX_TRAVERSAL_DEPTH", DEFAULT_MAX_DEPTH, minimum=0)


def _get_session_from_ctx(ctx: Any) -> object | None:
    if ctx is None:
        return None
    return getattr(ctx, "session", None)


def get_session_state(session: object) -> SessionState:
    with _registry_lock:
        state = _registry.get(session)
        if state is None:
            state = SessionState()
            _registry[session] = state
        return state


def record_search_origin(ctx: Any, results: list[dict[str, Any]]) -> None:
    session = _get_session_from_ctx(ctx)
    if session is None:
        return

    state = get_session_state(session)
    if state.origin_node_ids is not None:
        return

    origin_node_ids = {
        f"{result['file_path']}:{result['start_line']}"
        for result in results
        if result.get("file_path") and result.get("start_line") is not None
    }
    if origin_node_ids:
        state.origin_node_ids = frozenset(origin_node_ids)


def record_expand_definition(ctx: Any) -> None:
    session = _get_session_from_ctx(ctx)
    if session is None:
        return
    get_session_state(session).expand_definition_used = True


def _minimum_depth_to_origin(graph: Any, origin_node_ids: frozenset[str], target_node_id: str) -> int | None:
    if not hasattr(graph, "graph") or target_node_id not in graph.graph:
        return None

    undirected = graph.graph.to_undirected(as_view=True)
    min_depth: int | None = None
    for origin_node_id in origin_node_ids:
        if origin_node_id not in undirected:
            continue
        try:
            depth = nx.shortest_path_length(undirected, origin_node_id, target_node_id)
        except nx.NetworkXNoPath:
            continue
        if min_depth is None or depth < min_depth:
            min_depth = depth
    return min_depth


def safety_wrap_get_neighbors(
    node_id: str,
    ctx: Any,
    core_fn: Callable[[str], str],
    graph: Any,
) -> str:
    session = _get_session_from_ctx(ctx)
    if session is None:
        return core_fn(node_id)

    state = get_session_state(session)
    current_visit_count = state.visit_counts.get(node_id, 0)
    if current_visit_count >= get_revisit_threshold():
        return REVISIT_NOTICE

    if state.origin_node_ids and not state.expand_definition_used:
        depth = _minimum_depth_to_origin(graph, state.origin_node_ids, node_id)
        if depth is not None and depth > get_max_traversal_depth():
            return DEPTH_NOTICE

    result = core_fn(node_id)
    state.visit_counts[node_id] = current_visit_count + 1
    return result
