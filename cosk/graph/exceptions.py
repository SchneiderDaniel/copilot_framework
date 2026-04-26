from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EdgeLabel = Literal["imports", "calls"]


@dataclass(frozen=True, slots=True)
class CycleEdge:
    source_node_id: str
    target_node_id: str
    labels: tuple[EdgeLabel, ...]


class CycleError(Exception):
    def __init__(self, cycle_edges: list[CycleEdge]) -> None:
        self.cycle_edges = cycle_edges
        super().__init__(f"Cycle detected: {cycle_edges}")
