from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from rich.console import Console

import cosk.inspect as inspect_module


class _FakeSchema:
    names = ["node_id", "file_path", "start_line", "end_line", "raw_signature", "summary", "vector"]

    def field(self, name: str):  # noqa: ARG002
        vector_type = Mock()
        vector_type.list_size = 3
        field = Mock()
        field.type = vector_type
        return field


class _FakeArrowTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def to_pylist(self) -> list[dict[str, object]]:
        return self._rows


class _FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.schema = _FakeSchema()

    def to_arrow(self) -> _FakeArrowTable:
        return _FakeArrowTable(self._rows)


def _fake_rows() -> list[dict[str, object]]:
    return [
        {
            "node_id": "hash-1",
            "file_path": "a.py",
            "start_line": 1,
            "end_line": 3,
            "raw_signature": "def alpha(): pass",
            "summary": "alpha docs",
            "vector": [1.0, 0.0, 0.0],
        },
        {
            "node_id": "hash-2",
            "file_path": "b.py",
            "start_line": 5,
            "end_line": 6,
            "raw_signature": "def beta(): alpha()",
            "summary": "beta docs",
            "vector": [0.0, 1.0, 0.0],
        },
    ]


def test_parse_args_defaults_db_dir_to_package_lancedb() -> None:
    parsed = inspect_module.parse_args([])
    assert parsed.db_dir == Path(inspect_module.__file__).resolve().parent / ".lancedb"


def test_parse_args_accepts_custom_db_dir() -> None:
    parsed = inspect_module.parse_args(["--db-dir", "C:/tmp/custom.lancedb"])
    assert parsed.db_dir == Path("C:/tmp/custom.lancedb")


def test_run_returns_non_zero_for_missing_or_invalid_index(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = Mock()
    fake_store.validate_index.return_value = False
    monkeypatch.setattr(inspect_module, "SkeletonNodeVectorStore", Mock(return_value=fake_store))
    result = inspect_module.run([])
    assert result != 0


def test_run_returns_zero_for_valid_empty_index(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = Mock()
    fake_store.validate_index.return_value = True
    fake_store._table = _FakeTable([])  # noqa: SLF001
    monkeypatch.setattr(inspect_module, "SkeletonNodeVectorStore", Mock(return_value=fake_store))
    result = inspect_module.run([])
    assert result == 0


def test_build_report_collects_row_count_schema_sample_and_vector_dim(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _fake_rows()
    fake_store = Mock()
    fake_store.validate_index.return_value = True
    fake_store._table = _FakeTable(rows)  # noqa: SLF001
    monkeypatch.setattr(inspect_module, "SkeletonNodeVectorStore", Mock(return_value=fake_store))
    report = inspect_module.build_report(Path("C:/db"))
    assert report.vector.row_count == 2
    assert report.vector.columns == _FakeSchema.names
    assert report.vector.sample_rows == rows
    assert report.vector.vector_dim == 3


def test_graph_source_prefers_loaded_state_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded_graph = Mock()
    loaded_graph.graph.number_of_nodes.return_value = 1
    loaded_graph.graph.number_of_edges.return_value = 2
    monkeypatch.setattr(inspect_module.state, "get_graph", Mock(return_value=loaded_graph))
    build_graph_spy = Mock()
    monkeypatch.setattr(inspect_module, "build_graph", build_graph_spy)
    details, _ = inspect_module._graph_from_rows(_fake_rows())  # noqa: SLF001
    assert details.source == "state"
    build_graph_spy.assert_not_called()


def test_graph_source_falls_back_to_rebuild_when_state_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    rebuilt_graph = Mock()
    rebuilt_graph.graph.number_of_nodes.return_value = 3
    rebuilt_graph.graph.number_of_edges.return_value = 4
    monkeypatch.setattr(inspect_module.state, "get_graph", Mock(return_value=None))
    build_graph_spy = Mock(return_value=rebuilt_graph)
    monkeypatch.setattr(inspect_module, "build_graph", build_graph_spy)
    details, _ = inspect_module._graph_from_rows(_fake_rows())  # noqa: SLF001
    assert details.source == "rebuilt"
    build_graph_spy.assert_called_once()


def test_graph_rebuild_failure_degrades_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _fake_rows()
    fake_store = Mock()
    fake_store.validate_index.return_value = True
    fake_store._table = _FakeTable(rows)  # noqa: SLF001
    monkeypatch.setattr(inspect_module, "SkeletonNodeVectorStore", Mock(return_value=fake_store))
    monkeypatch.setattr(inspect_module.state, "get_graph", Mock(return_value=None))
    monkeypatch.setattr(inspect_module, "build_graph", Mock(side_effect=RuntimeError("broken graph")))
    result = inspect_module.run([])
    assert result == 0


def test_render_includes_all_required_sections() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=140)
    report = inspect_module.InspectReport(
        db_dir=Path("C:/db"),
        index_valid=True,
        vector=inspect_module.VectorDetails(
            table_name="skeleton_nodes",
            row_count=2,
            vector_dim=3,
            columns=_FakeSchema.names,
            all_rows=_fake_rows(),
            sample_rows=_fake_rows(),
        ),
        graph=inspect_module.GraphDetails(source="rebuilt", node_count=2, edge_count=1),
    )
    inspect_module.render_report(report, console)
    rendered = output.getvalue()
    assert "Header" in rendered
    assert "Indexed Nodes Table" in rendered
    assert "Graph Stats Table" in rendered
    assert "Vector DB Panel" in rendered
    assert "Tip: Use --db-dir to inspect a non-default index" in rendered
