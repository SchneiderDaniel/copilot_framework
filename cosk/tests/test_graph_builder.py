from __future__ import annotations

import networkx as nx
import pytest

from cosk.extraction.models import SkeletonNode
from cosk.graph import state
from cosk.graph.builder import RelationshipGraph, build_graph, compute_node_id, rebuild
from cosk.graph.exceptions import CycleError


@pytest.fixture(autouse=True)
def clear_singleton_graph() -> None:
    state.clear_graph()
    yield
    state.clear_graph()


def make_node(name_sig: str, file_path: str, line: int, extra_sig: str = "") -> SkeletonNode:
    return SkeletonNode(file_path, line, line, f"{name_sig}{extra_sig}", "")


def test_compute_node_id_uses_posix_absolute_path_and_start_line() -> None:
    node = make_node("def alpha():", "/repo/a.py", 1)
    assert compute_node_id(node) == "/repo/a.py:1"


def test_build_graph_returns_relationship_graph_wrapping_digraph() -> None:
    graph = build_graph([make_node("def alpha():", "/repo/a.py", 1)])
    assert isinstance(graph, RelationshipGraph)
    assert isinstance(graph.graph, nx.DiGraph)


def test_build_graph_adds_all_nodes_by_computed_id() -> None:
    nodes = [
        make_node("def alpha():", "/repo/a.py", 1),
        make_node("def beta():", "/repo/b.py", 5),
        make_node("def gamma():", "/repo/c.py", 10),
    ]
    graph = build_graph(nodes)
    assert set(graph.graph.nodes) == {compute_node_id(node) for node in nodes}


def test_build_graph_normalizes_function_signature_for_ast_parse() -> None:
    alpha = make_node("def alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    assert graph.has_edge(compute_node_id(alpha), compute_node_id(beta))


def test_build_graph_normalizes_async_function_signature_for_ast_parse() -> None:
    alpha = make_node("async def alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    assert graph.has_edge(compute_node_id(alpha), compute_node_id(beta))


def test_build_graph_normalizes_class_signature_for_ast_parse() -> None:
    alpha = make_node("class Alpha(beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    assert graph.has_edge(compute_node_id(alpha), compute_node_id(beta))


def test_build_graph_normalizes_decorator_prefixed_signature_for_ast_parse() -> None:
    alpha = make_node("@deco\ndef alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    assert graph.has_edge(compute_node_id(alpha), compute_node_id(beta))


def test_build_graph_creates_import_edge_for_ast_import() -> None:
    alpha = make_node("import beta", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    edge = graph.get_edge_data(compute_node_id(alpha), compute_node_id(beta))
    assert edge == {"labels": ("imports",)}


def test_build_graph_creates_import_edge_for_ast_importfrom() -> None:
    alpha = make_node("from mod import beta", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    edge = graph.get_edge_data(compute_node_id(alpha), compute_node_id(beta))
    assert edge == {"labels": ("imports",)}


def test_build_graph_creates_call_edge_for_simple_name_call() -> None:
    alpha = make_node("def alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    edge = graph.get_edge_data(compute_node_id(alpha), compute_node_id(beta))
    assert edge == {"labels": ("calls",)}


def test_build_graph_creates_call_edge_for_attribute_call_terminal_name() -> None:
    alpha = make_node("def alpha(x=pkg.beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    edge = graph.get_edge_data(compute_node_id(alpha), compute_node_id(beta))
    assert edge == {"labels": ("calls",)}


def test_build_graph_skips_unresolved_import_without_creating_synthetic_node() -> None:
    alpha = make_node("import missing", "/repo/a.py", 1)
    graph = build_graph([alpha]).graph
    assert set(graph.nodes) == {compute_node_id(alpha)}
    assert graph.number_of_edges() == 0


def test_build_graph_skips_unresolved_call_without_creating_synthetic_node() -> None:
    alpha = make_node("def alpha(x=missing()):", "/repo/a.py", 1)
    graph = build_graph([alpha]).graph
    assert set(graph.nodes) == {compute_node_id(alpha)}
    assert graph.number_of_edges() == 0


def test_build_graph_merges_imports_and_calls_labels_on_same_edge() -> None:
    alpha = make_node("import beta\ndef alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    graph = build_graph([alpha, beta]).graph
    edge = graph.get_edge_data(compute_node_id(alpha), compute_node_id(beta))
    assert edge == {"labels": ("calls", "imports")}


def test_get_neighbors_returns_expected_shape_and_one_entry_per_label() -> None:
    alpha = make_node("import beta\ndef alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta():", "/repo/b.py", 1)
    relationship_graph = build_graph([alpha, beta])
    neighbors = relationship_graph.get_neighbors(compute_node_id(alpha))
    assert neighbors == {
        "inbound": [],
        "outbound": [
            {"node_id": compute_node_id(beta), "label": "calls"},
            {"node_id": compute_node_id(beta), "label": "imports"},
        ],
    }


def test_get_neighbors_returns_deterministic_sorted_inbound_and_outbound() -> None:
    center = make_node(
        "import zeta\ndef center(a=alpha(), z=zeta()):",
        "/repo/center.py",
        1,
    )
    alpha = make_node("def alpha():", "/repo/alpha.py", 1)
    zeta = make_node("def zeta():", "/repo/zeta.py", 1)
    one = make_node("def one(x=center()):", "/repo/one.py", 1)
    two = make_node("import center", "/repo/two.py", 1)
    relationship_graph = build_graph([center, alpha, zeta, one, two])
    neighbors = relationship_graph.get_neighbors(compute_node_id(center))

    assert neighbors["inbound"] == sorted(
        neighbors["inbound"],
        key=lambda item: (item["node_id"], item["label"]),
    )
    assert neighbors["outbound"] == sorted(
        neighbors["outbound"],
        key=lambda item: (item["node_id"], item["label"]),
    )


def test_get_neighbors_unknown_node_returns_empty_lists() -> None:
    relationship_graph = build_graph([make_node("def alpha():", "/repo/a.py", 1)])
    assert relationship_graph.get_neighbors("/repo/missing.py:1") == {
        "inbound": [],
        "outbound": [],
    }


def test_build_graph_acyclic_does_not_raise_cycle_error() -> None:
    alpha = make_node("def alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta(x=gamma()):", "/repo/b.py", 1)
    gamma = make_node("def gamma():", "/repo/c.py", 1)
    build_graph([alpha, beta, gamma])


def test_build_graph_cycle_raises_cycle_error_with_cycle_edges() -> None:
    alpha = make_node("def alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta(x=alpha()):", "/repo/b.py", 1)
    with pytest.raises(CycleError):
        build_graph([alpha, beta])


def test_cycle_error_cycle_edges_include_expected_labels() -> None:
    alpha = make_node("def alpha(x=beta()):", "/repo/a.py", 1)
    beta = make_node("def beta(x=alpha()):", "/repo/b.py", 1)

    with pytest.raises(CycleError) as exc_info:
        build_graph([alpha, beta])

    cycle_edges = exc_info.value.cycle_edges
    assert cycle_edges
    for cycle_edge in cycle_edges:
        assert cycle_edge.source_node_id in {compute_node_id(alpha), compute_node_id(beta)}
        assert cycle_edge.target_node_id in {compute_node_id(alpha), compute_node_id(beta)}
        assert cycle_edge.labels == ("calls",)


def test_rebuild_sets_singleton_graph_in_state() -> None:
    result = rebuild([make_node("def alpha():", "/repo/a.py", 1)])
    assert state.get_graph() is result


def test_rebuild_replaces_existing_singleton_graph_instance() -> None:
    first = rebuild([make_node("def alpha():", "/repo/a.py", 1)])
    second = rebuild([make_node("def beta():", "/repo/b.py", 1)])
    assert first is not second
    assert state.get_graph() is second


def test_build_graph_is_pure_and_does_not_mutate_state_singleton() -> None:
    build_graph([make_node("def alpha():", "/repo/a.py", 1)])
    assert state.get_graph() is None


def test_clear_graph_resets_singleton_to_none() -> None:
    rebuild([make_node("def alpha():", "/repo/a.py", 1)])
    state.clear_graph()
    assert state.get_graph() is None


def test_state_get_set_clear_thread_safe_contract_smoke() -> None:
    graph = build_graph([make_node("def alpha():", "/repo/a.py", 1)])
    assert state.get_graph() is None
    state.set_graph(graph)
    assert state.get_graph() is graph
    state.clear_graph()
    assert state.get_graph() is None


def test_find_usages_returns_empty_list_for_unknown_entity() -> None:
    nodes = [make_node("def alpha():", "/repo/a.py", 1)]
    graph = build_graph(nodes)
    assert graph.find_usages("nonexistent") == []


def test_find_usages_returns_caller_for_direct_call_site() -> None:
    callee = make_node("def foo():", "/repo/callee.py", 1)
    caller = make_node("def bar(x=foo()):", "/repo/caller.py", 5)
    graph = build_graph([callee, caller])
    results = graph.find_usages("foo")
    assert len(results) == 1
    assert results[0]["file_path"] == "/repo/caller.py"
    assert results[0]["line"] == 5
    assert results[0]["context_node_id"] == compute_node_id(caller)


def test_find_usages_result_contains_required_keys() -> None:
    callee = make_node("def foo():", "/repo/a.py", 1)
    caller = make_node("def bar(x=foo()):", "/repo/b.py", 2)
    graph = build_graph([callee, caller])
    results = graph.find_usages("foo")
    assert results
    assert set(results[0]) == {"file_path", "line", "context_node_id"}


def test_find_usages_deduplicates_direct_and_graph_based_results() -> None:
    callee = make_node("def foo():", "/repo/a.py", 1)
    caller = make_node("def bar(x=foo()):", "/repo/b.py", 2)
    graph = build_graph([callee, caller])
    results = graph.find_usages("foo")
    node_ids = [entry["context_node_id"] for entry in results]
    assert len(node_ids) == len(set(node_ids))


def test_find_usages_returns_sorted_results() -> None:
    foo_def = make_node("def foo():", "/repo/z.py", 1)
    caller_a = make_node("def a(x=foo()):", "/repo/a.py", 1)
    caller_b = make_node("def b(x=foo()):", "/repo/b.py", 1)
    graph = build_graph([foo_def, caller_a, caller_b])
    results = graph.find_usages("foo")
    assert results == sorted(results, key=lambda entry: (entry["file_path"], entry["line"]))


def test_find_usages_finds_import_as_usage() -> None:
    foo_def = make_node("def foo():", "/repo/a.py", 1)
    importer = make_node("import foo", "/repo/b.py", 3)
    graph = build_graph([foo_def, importer])
    results = graph.find_usages("foo")
    assert any(entry["context_node_id"] == compute_node_id(importer) for entry in results)


def test_find_usages_excludes_defining_node_itself() -> None:
    foo_def = make_node("def foo():", "/repo/a.py", 1)
    graph = build_graph([foo_def])
    results = graph.find_usages("foo")
    assert not any(entry["context_node_id"] == compute_node_id(foo_def) for entry in results)


def test_build_graph_stores_node_attributes_for_find_usages() -> None:
    node = make_node("def alpha():", "/repo/a.py", 7)
    graph = build_graph([node])
    node_id = compute_node_id(node)
    attributes = graph.graph.nodes[node_id]
    assert attributes["file_path"] == "/repo/a.py"
    assert attributes["start_line"] == 7
    assert "raw_signature" in attributes
