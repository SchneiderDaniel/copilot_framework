from __future__ import annotations

if __name__ == "inspect":
    import importlib.util
    from pathlib import Path
    import sysconfig

    stdlib_inspect = Path(sysconfig.get_paths()["stdlib"]) / "inspect.py"
    spec = importlib.util.spec_from_file_location("inspect", stdlib_inspect)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("Unable to resolve stdlib inspect module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    globals().update(module.__dict__)
else:
    import argparse
    from dataclasses import dataclass
    from pathlib import Path
    from typing import Any, Protocol

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from cosk.extraction.models import SkeletonNode
    from cosk.graph import state
    from cosk.graph.builder import build_graph
    from cosk.indexing.vector_store import SkeletonNodeVectorStore

    class _EmbeddingProvider(Protocol):
        def embed(self, text: str) -> list[float]:
            ...

    class _NoopEmbeddingProvider:
        def embed(self, text: str) -> list[float]:  # noqa: ARG002
            raise RuntimeError("Embedding is not used by cosk.inspect")

    @dataclass(slots=True)
    class VectorDetails:
        table_name: str
        row_count: int
        vector_dim: int
        columns: list[str]
        all_rows: list[dict[str, Any]]
        sample_rows: list[dict[str, Any]]

    @dataclass(slots=True)
    class GraphDetails:
        source: str
        node_count: int
        edge_count: int
        unavailable_reason: str | None = None

    @dataclass(slots=True)
    class InspectReport:
        db_dir: Path
        index_valid: bool
        vector: VectorDetails
        graph: GraphDetails

    def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
        parser = argparse.ArgumentParser(description="Inspect a Cosk LanceDB index and graph state.")
        parser.add_argument(
            "--db-dir",
            type=Path,
            default=Path(__file__).resolve().parent / ".lancedb",
            help="LanceDB directory path.",
        )
        return parser.parse_args(argv)

    def _read_table_rows(table: Any) -> list[dict[str, Any]]:
        arrow_table = table.to_arrow()
        return arrow_table.to_pylist()

    def _vector_dim_from_table(table: Any, rows: list[dict[str, Any]]) -> int:
        try:
            vector_field = table.schema.field("vector")
            list_size = getattr(vector_field.type, "list_size", None)
            if isinstance(list_size, int) and list_size > 0:
                return list_size
        except Exception:  # noqa: BLE001
            pass

        for row in rows:
            vector = row.get("vector")
            if isinstance(vector, list) and vector:
                return len(vector)
        return 0

    def _graph_from_rows(rows: list[dict[str, Any]]) -> tuple[GraphDetails, Any]:
        loaded_graph = state.get_graph()
        if loaded_graph is not None:
            return (
                GraphDetails(
                    source="state",
                    node_count=loaded_graph.graph.number_of_nodes(),
                    edge_count=loaded_graph.graph.number_of_edges(),
                ),
                loaded_graph,
            )

        nodes = [
            SkeletonNode(
                file_path=str(row.get("file_path", "")),
                start_line=int(row.get("start_line", 0)),
                end_line=int(row.get("end_line", 0)),
                raw_signature=str(row.get("raw_signature", "")),
                docstring=str(row.get("summary", "")),
            )
            for row in rows
        ]

        try:
            rebuilt_graph = build_graph(nodes)
            return (
                GraphDetails(
                    source="rebuilt",
                    node_count=rebuilt_graph.graph.number_of_nodes(),
                    edge_count=rebuilt_graph.graph.number_of_edges(),
                ),
                rebuilt_graph,
            )
        except Exception as exc:  # noqa: BLE001
            return (
                GraphDetails(source="unavailable", node_count=0, edge_count=0, unavailable_reason=str(exc)),
                None,
            )

    def build_report(db_dir: Path) -> InspectReport:
        vector_store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=_NoopEmbeddingProvider())
        index_valid = vector_store.validate_index()
        if not index_valid:
            raise RuntimeError(f"Missing or invalid index at '{db_dir}'.")

        table = vector_store._table if hasattr(vector_store, "_table") else None  # noqa: SLF001
        if table is None:
            db = vector_store._connect()  # noqa: SLF001
            table = db.open_table("skeleton_nodes")

        rows = _read_table_rows(table)
        vector = VectorDetails(
            table_name="skeleton_nodes",
            row_count=len(rows),
            vector_dim=_vector_dim_from_table(table, rows),
            columns=list(table.schema.names),
            all_rows=rows,
            sample_rows=rows[:10],
        )
        graph, _ = _graph_from_rows(rows)

        return InspectReport(db_dir=db_dir, index_valid=index_valid, vector=vector, graph=graph)

    def _format_signature(value: str, *, limit: int = 50) -> str:
        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3] + "..."

    def _build_indexed_nodes_table(rows: list[dict[str, Any]]) -> Table:
        table = Table(title="Indexed Nodes")
        table.add_column("node_id")
        table.add_column("file_path")
        table.add_column("start_line")
        table.add_column("end_line")
        table.add_column("raw_signature")

        for row in rows[:20]:
            table.add_row(
                str(row.get("node_id", "")),
                str(row.get("file_path", "")),
                str(row.get("start_line", "")),
                str(row.get("end_line", "")),
                _format_signature(str(row.get("raw_signature", ""))),
            )
        return table

    def _build_graph_stats_table(graph: GraphDetails) -> Table:
        table = Table(title="Graph Stats")
        table.add_column("metric")
        table.add_column("value")
        table.add_row("node_count", str(graph.node_count))
        table.add_row("edge_count", str(graph.edge_count))
        if graph.source == "unavailable" and graph.unavailable_reason:
            table.add_row("status", f"unavailable: {graph.unavailable_reason}")
        return table

    def _build_vector_panel(vector: VectorDetails) -> Panel:
        sample_table = Table(title="Vector DB")
        sample_table.add_column("field")
        sample_table.add_column("value")
        sample_table.add_row("table_name", vector.table_name)
        sample_table.add_row("row_count", str(vector.row_count))
        sample_table.add_row("vector_dim", str(vector.vector_dim))
        sample_table.add_row("columns", ", ".join(vector.columns))
        sample_table.add_row("sample_preview", str(vector.sample_rows))
        return Panel(sample_table, title="Vector DB Panel")

    def render_report(report: InspectReport, console: Console) -> None:
        header = (
            f"db_path={report.db_dir}\n"
            f"index_valid={report.index_valid}\n"
            f"graph_source={report.graph.source}"
        )
        console.print(Panel(header, title="Header"))
        console.print(Panel(_build_indexed_nodes_table(report.vector.all_rows), title="Indexed Nodes Table"))
        console.print(Panel(_build_graph_stats_table(report.graph), title="Graph Stats Table"))
        console.print(_build_vector_panel(report.vector))
        console.print(Panel("Tip: Use --db-dir to inspect a non-default index", title="Footer"))

    def run(argv: list[str] | None = None, *, console: Console | None = None) -> int:
        args = parse_args(argv)
        current_console = console or Console()
        try:
            report = build_report(args.db_dir)
        except Exception as exc:  # noqa: BLE001
            current_console.print(Panel(str(exc), title="Error"))
            return 1

        render_report(report, current_console)
        return 0

    def main(argv: list[str] | None = None) -> None:
        raise SystemExit(run(argv))

    if __name__ == "__main__":
        main()
