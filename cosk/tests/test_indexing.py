from __future__ import annotations

from pathlib import Path

from cosk.extraction.models import SkeletonNode
from cosk.indexing.vector_store import SkeletonNodeVectorStore


def test_upsert_validate_search_and_no_duplicates_after_double_upsert(
    fixture_nodes: list[SkeletonNode], indexed_vector_store: SkeletonNodeVectorStore
) -> None:
    indexed_vector_store.upsert_nodes(fixture_nodes)
    indexed_vector_store.upsert_nodes(fixture_nodes)

    assert indexed_vector_store.validate_index() is True
    results = indexed_vector_store.search("wrapper", top_k=10)
    assert results
    node_ids = [entry["node_id"] for entry in results]
    assert len(node_ids) == len(set(node_ids))


def test_indexing_uses_only_tmp_lancedb_path(indexed_vector_store: SkeletonNodeVectorStore, tmp_path: Path) -> None:
    assert indexed_vector_store._db_dir == tmp_path / ".lancedb"  # noqa: SLF001
