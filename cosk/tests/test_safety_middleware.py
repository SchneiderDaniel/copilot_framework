from __future__ import annotations

import gc

import networkx as nx
import pytest

from cosk.graph.builder import RelationshipGraph
from cosk.safety import middleware


class _Session:
    pass


class _Context:
    def __init__(self, session: _Session) -> None:
        self.session = session


@pytest.fixture(autouse=True)
def _clear_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware._registry.clear()  # noqa: SLF001
    monkeypatch.delenv("COSK_REVISIT_THRESHOLD", raising=False)
    monkeypatch.delenv("COSK_MAX_TRAVERSAL_DEPTH", raising=False)


def _graph_with_edges(*edges: tuple[str, str]) -> RelationshipGraph:
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    return RelationshipGraph(graph=graph)


def _ctx() -> _Context:
    return _Context(_Session())


def test_ctx_none_bypasses_session_tracking() -> None:
    call_count = 0

    def _core(node_id: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"ok:{node_id}"

    result = middleware.safety_wrap_get_neighbors("a.py:1", None, _core, _graph_with_edges())
    assert result == "ok:a.py:1"
    assert call_count == 1
    assert len(middleware._registry) == 0  # noqa: SLF001


def test_first_visit_allowed_with_default_threshold() -> None:
    ctx = _ctx()
    result = middleware.safety_wrap_get_neighbors("a.py:1", ctx, lambda node_id: node_id, _graph_with_edges())
    assert result == "a.py:1"
    assert middleware.get_session_state(ctx.session).visit_counts["a.py:1"] == 1


def test_second_visit_blocked_with_revisit_notice() -> None:
    ctx = _ctx()
    call_count = 0

    def _core(_: str) -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    assert middleware.safety_wrap_get_neighbors("a.py:1", ctx, _core, _graph_with_edges()) == "ok"
    assert (
        middleware.safety_wrap_get_neighbors("a.py:1", ctx, _core, _graph_with_edges()) == middleware.REVISIT_NOTICE
    )
    assert call_count == 1


def test_configurable_revisit_threshold_two_allows_two_blocks_third(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSK_REVISIT_THRESHOLD", "2")
    ctx = _ctx()
    assert middleware.safety_wrap_get_neighbors("a.py:1", ctx, lambda _: "ok", _graph_with_edges()) == "ok"
    assert middleware.safety_wrap_get_neighbors("a.py:1", ctx, lambda _: "ok", _graph_with_edges()) == "ok"
    assert (
        middleware.safety_wrap_get_neighbors("a.py:1", ctx, lambda _: "ok", _graph_with_edges())
        == middleware.REVISIT_NOTICE
    )


def test_revisit_block_is_session_scoped() -> None:
    session_one_ctx = _ctx()
    session_two_ctx = _ctx()
    assert middleware.safety_wrap_get_neighbors("a.py:1", session_one_ctx, lambda _: "ok", _graph_with_edges()) == "ok"
    assert (
        middleware.safety_wrap_get_neighbors("a.py:1", session_one_ctx, lambda _: "ok", _graph_with_edges())
        == middleware.REVISIT_NOTICE
    )
    assert middleware.safety_wrap_get_neighbors("a.py:1", session_two_ctx, lambda _: "ok", _graph_with_edges()) == "ok"


def test_origin_is_seeded_from_first_non_empty_search_only() -> None:
    ctx = _ctx()
    middleware.record_search_origin(ctx, [])
    assert middleware.get_session_state(ctx.session).origin_node_ids is None

    middleware.record_search_origin(ctx, [{"file_path": "a.py", "start_line": 7, "node_id": "ignored"}])
    assert middleware.get_session_state(ctx.session).origin_node_ids == frozenset({"a.py:7"})


def test_origin_uses_graph_node_id_format_not_search_hash() -> None:
    ctx = _ctx()
    middleware.record_search_origin(ctx, [{"file_path": "a.py", "start_line": 10, "node_id": "hash-id"}])
    assert middleware.get_session_state(ctx.session).origin_node_ids == frozenset({"a.py:10"})


def test_origin_never_resets_on_later_searches() -> None:
    ctx = _ctx()
    middleware.record_search_origin(ctx, [{"file_path": "a.py", "start_line": 1}])
    middleware.record_search_origin(ctx, [{"file_path": "b.py", "start_line": 2}])
    assert middleware.get_session_state(ctx.session).origin_node_ids == frozenset({"a.py:1"})


def test_depth_blocks_when_more_than_three_hops() -> None:
    graph = _graph_with_edges(("n0", "n1"), ("n1", "n2"), ("n2", "n3"), ("n3", "n4"))
    ctx = _ctx()
    middleware.get_session_state(ctx.session).origin_node_ids = frozenset({"n0"})
    assert middleware.safety_wrap_get_neighbors("n4", ctx, lambda _: "ok", graph) == middleware.DEPTH_NOTICE


def test_depth_allows_when_within_three_hops() -> None:
    graph = _graph_with_edges(("n0", "n1"), ("n1", "n2"), ("n2", "n3"), ("n3", "n4"))
    ctx = _ctx()
    middleware.get_session_state(ctx.session).origin_node_ids = frozenset({"n0"})
    assert middleware.safety_wrap_get_neighbors("n3", ctx, lambda _: "ok", graph) == "ok"


def test_depth_uses_min_distance_across_multi_origin() -> None:
    graph = _graph_with_edges(
        ("n0", "n1"),
        ("n1", "n2"),
        ("n2", "n3"),
        ("n3", "n4"),
        ("n4", "n5"),
        ("n5", "n6"),
        ("n6", "n7"),
        ("n7", "n8"),
        ("n10", "n9"),
        ("n9", "n8"),
    )
    ctx = _ctx()
    middleware.get_session_state(ctx.session).origin_node_ids = frozenset({"n0", "n10"})
    assert middleware.safety_wrap_get_neighbors("n8", ctx, lambda _: "ok", graph) == "ok"


def test_depth_is_undirected_for_reverse_only_edges() -> None:
    graph = _graph_with_edges(("n1", "n0"), ("n2", "n1"), ("n3", "n2"), ("n4", "n3"))
    ctx = _ctx()
    middleware.get_session_state(ctx.session).origin_node_ids = frozenset({"n0"})
    assert middleware.safety_wrap_get_neighbors("n4", ctx, lambda _: "ok", graph) == middleware.DEPTH_NOTICE


def test_no_path_allows_without_depth_block() -> None:
    graph = _graph_with_edges(("n0", "n1"), ("n10", "n11"))
    ctx = _ctx()
    middleware.get_session_state(ctx.session).origin_node_ids = frozenset({"n0"})
    assert middleware.safety_wrap_get_neighbors("n11", ctx, lambda _: "ok", graph) == "ok"


def test_expand_definition_unlocks_depth_blocking() -> None:
    graph = _graph_with_edges(("n0", "n1"), ("n1", "n2"), ("n2", "n3"), ("n3", "n4"))
    ctx = _ctx()
    middleware.get_session_state(ctx.session).origin_node_ids = frozenset({"n0"})
    middleware.record_expand_definition(ctx)
    assert middleware.safety_wrap_get_neighbors("n4", ctx, lambda _: "ok", graph) == "ok"


def test_weak_key_registry_cleans_up_after_session_gc() -> None:
    session = _Session()
    middleware.get_session_state(session)
    assert len(middleware._registry) == 1  # noqa: SLF001
    del session
    gc.collect()
    assert len(middleware._registry) == 0  # noqa: SLF001


def test_invalid_env_values_fallback_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COSK_REVISIT_THRESHOLD", "invalid")
    revisit_ctx = _ctx()
    assert middleware.safety_wrap_get_neighbors("a.py:1", revisit_ctx, lambda _: "ok", _graph_with_edges()) == "ok"
    assert (
        middleware.safety_wrap_get_neighbors("a.py:1", revisit_ctx, lambda _: "ok", _graph_with_edges())
        == middleware.REVISIT_NOTICE
    )

    monkeypatch.setenv("COSK_MAX_TRAVERSAL_DEPTH", "invalid")
    depth_ctx = _ctx()
    graph = _graph_with_edges(("n0", "n1"), ("n1", "n2"), ("n2", "n3"), ("n3", "n4"))
    middleware.get_session_state(depth_ctx.session).origin_node_ids = frozenset({"n0"})
    assert middleware.safety_wrap_get_neighbors("n4", depth_ctx, lambda _: "ok", graph) == middleware.DEPTH_NOTICE
