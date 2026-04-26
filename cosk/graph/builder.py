from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

import networkx as nx

from cosk.extraction.models import SkeletonNode
from cosk.graph.exceptions import CycleEdge, CycleError, EdgeLabel


class NeighborEntry(TypedDict):
    node_id: str
    label: EdgeLabel


class NeighborMap(TypedDict):
    inbound: list[NeighborEntry]
    outbound: list[NeighborEntry]


def compute_node_id(node: SkeletonNode) -> str:
    return f"{node.file_path}:{node.start_line}"


def _normalize_signature_for_ast(raw_signature: str) -> str:
    normalized = raw_signature.strip()
    if not normalized:
        return normalized

    lines = normalized.splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "async def ", "class ")) and stripped.endswith(":"):
            return f"{normalized}\n    pass"

    return normalized


def _extract_defined_name(raw_signature: str) -> str | None:
    normalized = _normalize_signature_for_ast(raw_signature)
    if not normalized:
        return None

    try:
        tree = ast.parse(normalized)
    except SyntaxError:
        return None

    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return statement.name

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            first_alias = statement.names[0]
            return first_alias.asname or first_alias.name.split(".")[0]
        if isinstance(statement, ast.ImportFrom):
            first_alias = statement.names[0]
            return first_alias.asname or first_alias.name

    return None


def _collect_import_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _collect_call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _extract_reference_names(raw_signature: str) -> dict[EdgeLabel, set[str]]:
    normalized = _normalize_signature_for_ast(raw_signature)
    if not normalized:
        return {"imports": set(), "calls": set()}

    try:
        tree = ast.parse(normalized)
    except SyntaxError:
        return {"imports": set(), "calls": set()}

    return {
        "imports": _collect_import_names(tree),
        "calls": _collect_call_names(tree),
    }


def _add_edge_label(graph: nx.DiGraph, src_id: str, tgt_id: str, label: EdgeLabel) -> None:
    if graph.has_edge(src_id, tgt_id):
        labels = graph[src_id][tgt_id].get("labels", ())
        if label not in labels:
            graph[src_id][tgt_id]["labels"] = tuple(sorted((*labels, label)))
        return
    graph.add_edge(src_id, tgt_id, labels=(label,))


@dataclass(slots=True)
class RelationshipGraph:
    graph: nx.DiGraph

    def get_neighbors(self, node_id: str) -> NeighborMap:
        if node_id not in self.graph:
            return {"inbound": [], "outbound": []}

        inbound: list[NeighborEntry] = []
        outbound: list[NeighborEntry] = []

        for source_id in self.graph.predecessors(node_id):
            labels = self.graph[source_id][node_id].get("labels", ())
            for label in labels:
                inbound.append({"node_id": source_id, "label": label})

        for target_id in self.graph.successors(node_id):
            labels = self.graph[node_id][target_id].get("labels", ())
            for label in labels:
                outbound.append({"node_id": target_id, "label": label})

        inbound.sort(key=lambda item: (item["node_id"], item["label"]))
        outbound.sort(key=lambda item: (item["node_id"], item["label"]))
        return {"inbound": inbound, "outbound": outbound}

    def detect_cycles(self) -> None:
        try:
            raw_cycle = nx.find_cycle(self.graph)
        except nx.NetworkXNoCycle:
            return

        cycle_edges: list[CycleEdge] = []
        for edge in raw_cycle:
            source_id, target_id = edge[0], edge[1]
            labels = self.graph[source_id][target_id].get("labels", ())
            cycle_edges.append(
                CycleEdge(
                    source_node_id=source_id,
                    target_node_id=target_id,
                    labels=labels,
                )
            )
        raise CycleError(cycle_edges)


def build_graph(nodes: Sequence[SkeletonNode]) -> RelationshipGraph:
    graph = nx.DiGraph()
    definitions_by_name: dict[str, list[str]] = defaultdict(list)

    for node in nodes:
        node_id = compute_node_id(node)
        graph.add_node(node_id)

        defined_name = _extract_defined_name(node.raw_signature) or node_id
        definitions_by_name[defined_name].append(node_id)

    for source_node in nodes:
        source_node_id = compute_node_id(source_node)
        reference_names = _extract_reference_names(source_node.raw_signature)
        for label, names in reference_names.items():
            for name in names:
                for target_node_id in definitions_by_name.get(name, []):
                    if target_node_id == source_node_id:
                        continue
                    _add_edge_label(graph, source_node_id, target_node_id, label)

    relationship_graph = RelationshipGraph(graph)
    relationship_graph.detect_cycles()
    return relationship_graph


def rebuild(nodes: Sequence[SkeletonNode]) -> RelationshipGraph:
    graph = build_graph(nodes)
    from cosk.graph import state

    state.set_graph(graph)
    return graph
