from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cosk.extraction.models import SkeletonNode
from cosk.indexing.vector_store import SkeletonNodeVectorStore


class FakeEmbeddingProvider:
    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        if not self._vectors:
            raise RuntimeError("No vectors configured")
        return self._vectors.pop(0)


def _sample_node(
    start_line: int = 10,
    *,
    signature: str = "def run() -> None:",
    docstring: str = "docs",
) -> SkeletonNode:
    return SkeletonNode("pkg/file.py", start_line, start_line + 2, signature, docstring)


def test_compute_node_id_matches_sha256_file_path_colon_start_line() -> None:
    node = _sample_node(start_line=11)
    expected = hashlib.sha256("pkg/file.py:11".encode("utf-8")).hexdigest()
    assert SkeletonNodeVectorStore.compute_node_id(node) == expected


def test_compute_node_id_changes_when_start_line_changes() -> None:
    assert SkeletonNodeVectorStore.compute_node_id(_sample_node(start_line=1)) != SkeletonNodeVectorStore.compute_node_id(
        _sample_node(start_line=2)
    )


def test_init_uses_injected_embedding_provider_when_provided() -> None:
    provider = FakeEmbeddingProvider([[1.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    assert store._embedding_provider is provider  # noqa: SLF001


def test_init_constructs_gemini_provider_when_embedding_provider_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = object()
    cls = MagicMock(return_value=fake_provider)
    monkeypatch.setattr("cosk.indexing.vector_store.GeminiEmbeddingProvider", cls)
    store = SkeletonNodeVectorStore()
    cls.assert_called_once()
    assert store._embedding_provider is fake_provider  # noqa: SLF001


def test_upsert_nodes_returns_zero_for_empty_input_without_db_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SkeletonNodeVectorStore(embedding_provider=FakeEmbeddingProvider([[1.0]]))
    connect = MagicMock()
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", connect)
    assert store.upsert_nodes([]) == 0
    connect.assert_not_called()


def test_upsert_nodes_builds_rows_with_required_metadata_and_summary_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0, 2.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    merge = MagicMock()
    table = MagicMock()
    table.merge_insert.return_value = merge
    merge.when_matched_update_all.return_value = merge
    merge.when_not_matched_insert_all.return_value = merge
    db = MagicMock()
    db.list_tables.return_value = []
    db.table_names.return_value = []
    db.open_table.side_effect = RuntimeError("missing")
    db.create_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))

    node = _sample_node()
    store.upsert_nodes([node])

    rows = merge.execute.call_args.args[0]
    assert len(rows) == 1
    row = rows[0]
    assert row["node_id"] == SkeletonNodeVectorStore.compute_node_id(node)
    assert row["file_path"] == node.file_path
    assert row["start_line"] == node.start_line
    assert row["end_line"] == node.end_line
    assert row["raw_signature"] == node.raw_signature
    assert row["summary"] == node.docstring


def test_upsert_nodes_uses_merge_insert_upsert_contract_on_node_id(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    merge = MagicMock()
    table = MagicMock()
    table.merge_insert.return_value = merge
    merge.when_matched_update_all.return_value = merge
    merge.when_not_matched_insert_all.return_value = merge
    db = MagicMock()
    db.list_tables.return_value = []
    db.table_names.return_value = []
    db.open_table.side_effect = RuntimeError("missing")
    db.create_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))

    store.upsert_nodes([_sample_node()])

    table.merge_insert.assert_called_once_with("node_id")
    merge.when_matched_update_all.assert_called_once()
    merge.when_not_matched_insert_all.assert_called_once()
    merge.execute.assert_called_once()


def test_upsert_nodes_returns_count_of_processed_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0], [1.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    merge = MagicMock()
    table = MagicMock()
    table.merge_insert.return_value = merge
    merge.when_matched_update_all.return_value = merge
    merge.when_not_matched_insert_all.return_value = merge
    db = MagicMock()
    db.list_tables.return_value = []
    db.table_names.return_value = []
    db.open_table.side_effect = RuntimeError("missing")
    db.create_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))

    count = store.upsert_nodes([_sample_node(1), _sample_node(2)])
    assert count == 2


def test_upsert_nodes_rejects_vector_dimension_mismatch_across_nodes() -> None:
    provider = FakeEmbeddingProvider([[1.0], [1.0, 2.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    with pytest.raises(ValueError, match="dimension mismatch across nodes"):
        store.upsert_nodes([_sample_node(1), _sample_node(2)])


def test_upsert_nodes_creates_table_with_vector_dim_from_first_embedding_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0, 2.0, 3.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    merge = MagicMock()
    table = MagicMock()
    table.merge_insert.return_value = merge
    merge.when_matched_update_all.return_value = merge
    merge.when_not_matched_insert_all.return_value = merge
    db = MagicMock()
    db.list_tables.return_value = []
    db.table_names.return_value = []
    db.open_table.side_effect = RuntimeError("missing")
    db.create_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))

    store.upsert_nodes([_sample_node()])

    schema = db.create_table.call_args.kwargs["schema"]
    vector_field = schema.field("vector")
    assert vector_field.type.list_size == 3


@pytest.mark.parametrize("query", ["", "   "])
def test_search_raises_for_empty_query(query: str) -> None:
    store = SkeletonNodeVectorStore(embedding_provider=FakeEmbeddingProvider([[1.0]]))
    with pytest.raises(ValueError, match="must not be empty"):
        store.search(query)


@pytest.mark.parametrize("top_k", [0, -1])
def test_search_raises_for_non_positive_top_k(top_k: int) -> None:
    store = SkeletonNodeVectorStore(embedding_provider=FakeEmbeddingProvider([[1.0]]))
    with pytest.raises(ValueError, match="top_k must be > 0"):
        store.search("query", top_k=top_k)


def test_search_returns_empty_list_when_table_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SkeletonNodeVectorStore(embedding_provider=FakeEmbeddingProvider([[1.0]]))
    db = MagicMock()
    db.list_tables.return_value = []
    db.table_names.return_value = []
    db.open_table.side_effect = RuntimeError("missing")
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))
    assert store.search("query") == []


def test_search_embeds_query_and_applies_top_k_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0, 2.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    table = MagicMock()
    table.search.return_value.limit.return_value.to_list.return_value = []
    db = MagicMock()
    db.list_tables.return_value = ["skeleton_nodes"]
    db.table_names.return_value = ["skeleton_nodes"]
    db.open_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))

    store._vector_dim = 2  # noqa: SLF001
    store.search("query", top_k=3)

    assert provider.calls == ["query"]
    table.search.return_value.limit.assert_called_once_with(3)


def test_search_default_top_k_is_5(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    table = MagicMock()
    table.search.return_value.limit.return_value.to_list.return_value = []
    db = MagicMock()
    db.list_tables.return_value = ["skeleton_nodes"]
    db.table_names.return_value = ["skeleton_nodes"]
    db.open_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))

    store._vector_dim = 1  # noqa: SLF001
    store.search("query")
    table.search.return_value.limit.assert_called_once_with(5)


def test_search_returns_metadata_only_dicts(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    table = MagicMock()
    table.search.return_value.limit.return_value.to_list.return_value = [
        {
            "node_id": "id-1",
            "file_path": "x.py",
            "start_line": 1,
            "end_line": 2,
            "raw_signature": "def x()",
            "summary": "docs",
            "vector": [1.0],
            "_distance": 0.1,
        }
    ]
    db = MagicMock()
    db.list_tables.return_value = ["skeleton_nodes"]
    db.table_names.return_value = ["skeleton_nodes"]
    db.open_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))
    store._vector_dim = 1  # noqa: SLF001

    results = store.search("query")
    assert results == [
        {
            "node_id": "id-1",
            "file_path": "x.py",
            "start_line": 1,
            "end_line": 2,
            "raw_signature": "def x()",
            "summary": "docs",
        }
    ]


def test_search_rejects_query_vector_dimension_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0, 2.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    table = MagicMock()
    db = MagicMock()
    db.list_tables.return_value = ["skeleton_nodes"]
    db.table_names.return_value = ["skeleton_nodes"]
    db.open_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))
    store._vector_dim = 1  # noqa: SLF001
    with pytest.raises(ValueError, match="dimension mismatch"):
        store.search("query")


def test_delete_by_file_paths_issues_delete_query(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SkeletonNodeVectorStore(embedding_provider=FakeEmbeddingProvider([[1.0]]))
    table = MagicMock()
    db = MagicMock()
    db.open_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))
    deleted = store.delete_by_file_paths(["a.py"])
    assert deleted == 1
    table.delete.assert_called_once()


def test_vector_store_validate_index_false_when_missing(tmp_path: Path) -> None:
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=FakeEmbeddingProvider([[1.0]]))
    assert store.validate_index() is False


def test_vector_store_validate_index_false_when_invalid_schema(tmp_path: Path) -> None:
    db_dir = tmp_path / ".lancedb"
    db = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=FakeEmbeddingProvider([[1.0]]))._connect()  # noqa: SLF001
    db.create_table("skeleton_nodes", data=[{"node_id": "x", "vector": [1.0]}])
    store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=FakeEmbeddingProvider([[1.0]]))
    assert store.validate_index() is False


def test_vector_store_validate_index_true_for_valid_index(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0]])
    db_dir = tmp_path / ".lancedb"
    store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=provider)
    store.rebuild_index([_sample_node()])
    assert store.validate_index() is True


def test_vector_store_supports_empty_index_without_search_failure(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0], [1.0, 0.0]])
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    store.rebuild_index([])
    assert store.search("anything") == []


def test_vector_store_rebuild_replaces_existing_index(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]])
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    node_a = _sample_node(start_line=1, signature="def alpha() -> None:")
    node_b = _sample_node(start_line=2, signature="def beta() -> None:")
    store.rebuild_index([node_a])
    assert store.search("query-a")[0]["node_id"] == SkeletonNodeVectorStore.compute_node_id(node_a)
    store.rebuild_index([node_b])
    assert store.search("query-b")[0]["node_id"] == SkeletonNodeVectorStore.compute_node_id(node_b)


def test_upsert_same_node_twice_uses_same_node_id(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FakeEmbeddingProvider([[1.0], [1.0]])
    store = SkeletonNodeVectorStore(embedding_provider=provider)
    merge = MagicMock()
    table = MagicMock()
    table.merge_insert.return_value = merge
    merge.when_matched_update_all.return_value = merge
    merge.when_not_matched_insert_all.return_value = merge
    db = MagicMock()
    db.list_tables.side_effect = [[], ["skeleton_nodes"]]
    db.table_names.side_effect = [[], ["skeleton_nodes"]]
    db.open_table.side_effect = [RuntimeError("missing"), table]
    db.create_table.return_value = table
    monkeypatch.setattr("cosk.indexing.vector_store.lancedb.connect", MagicMock(return_value=db))
    node = _sample_node()

    store.upsert_nodes([node])
    first_rows = merge.execute.call_args.args[0]
    store.upsert_nodes([node])
    second_rows = merge.execute.call_args.args[0]
    assert first_rows[0]["node_id"] == second_rows[0]["node_id"]


@pytest.mark.integration
def test_vector_store_roundtrip_with_real_lancedb_and_fake_embedding_provider(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0], [1.0, 0.0]])
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    node = _sample_node()
    assert store.upsert_nodes([node]) == 1

    results = store.search("query", top_k=5)
    assert len(results) == 1
    assert results[0]["node_id"] == SkeletonNodeVectorStore.compute_node_id(node)


@pytest.mark.integration
def test_vector_store_reindex_same_node_no_duplicate_rows_real_lancedb(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    node = _sample_node()
    store.upsert_nodes([node])
    store.upsert_nodes([node])

    db = store._connect()  # noqa: SLF001
    table = db.open_table("skeleton_nodes")
    rows = table.search([1.0, 0.0]).limit(10).to_list()
    assert len(rows) == 1


@pytest.mark.integration
def test_vector_store_real_lancedb_missing_table_search_returns_empty(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0]])
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    assert store.search("query") == []


@pytest.mark.integration
def test_vector_store_real_lancedb_dimension_mismatch_raises(tmp_path: Path) -> None:
    provider = FakeEmbeddingProvider([[1.0, 0.0], [1.0]])
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=provider)
    store.upsert_nodes([_sample_node()])
    with pytest.raises(ValueError, match="dimension mismatch"):
        store.search("query")
