from __future__ import annotations

import pytest

from cosk.extraction.models import SkeletonNode
from cosk.graph.builder import build_graph, compute_node_id
from cosk.graph.exceptions import CycleError


def _node_with_signature(nodes: list[SkeletonNode], marker: str) -> SkeletonNode:
    return next(node for node in nodes if marker in node.raw_signature)


def test_get_neighbors_returns_expected_inbound_outbound_for_wrapper_node(fixture_nodes: list[SkeletonNode]) -> None:
    graph = build_graph(fixture_nodes)

    wrapper_node = _node_with_signature(fixture_nodes, "def wrapper(")
    consumer_node = _node_with_signature(fixture_nodes, "def consume(")
    helper_node = _node_with_signature(fixture_nodes, "def helper(")

    neighbors = graph.get_neighbors(compute_node_id(wrapper_node))
    assert {"node_id": compute_node_id(consumer_node), "label": "calls"} in neighbors["inbound"]
    assert {"node_id": compute_node_id(helper_node), "label": "calls"} in neighbors["outbound"]


def test_build_graph_cycle_detection_raises_cycle_error() -> None:
    alpha = SkeletonNode(
        file_path="/synthetic/alpha.py",
        start_line=1,
        end_line=1,
        raw_signature="def alpha(dep=beta()):",
        docstring="",
    )
    beta = SkeletonNode(
        file_path="/synthetic/beta.py",
        start_line=1,
        end_line=1,
        raw_signature="def beta(dep=alpha()):",
        docstring="",
    )

    with pytest.raises(CycleError) as exc_info:
        build_graph([alpha, beta])

    assert exc_info.value.cycle_edges
    assert all(cycle_edge.labels == ("calls",) for cycle_edge in exc_info.value.cycle_edges)
