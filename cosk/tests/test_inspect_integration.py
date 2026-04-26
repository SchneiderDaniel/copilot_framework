from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from cosk.extraction.models import SkeletonNode
from cosk.indexing.vector_store import SkeletonNodeVectorStore

pytestmark = pytest.mark.integration

COSK_DIR = Path(__file__).resolve().parents[1]


class _FakeEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        base = float(len(text) % 5)
        return [base, base + 1.0, base + 2.0]


def _run_inspect(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cosk.inspect", *args],
        cwd=COSK_DIR,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_inspect_help_includes_db_dir() -> None:
    completed = _run_inspect(["--help"])
    assert completed.returncode == 0
    assert "--db-dir" in completed.stdout


def test_inspect_happy_path_with_populated_index(tmp_path: Path) -> None:
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=_FakeEmbeddingProvider())
    store.rebuild_index(
        [
            SkeletonNode("a.py", 1, 2, "def alpha():", "docs"),
            SkeletonNode("b.py", 1, 2, "def beta():\n    alpha()", "docs"),
        ]
    )
    completed = _run_inspect(["--db-dir", str(tmp_path / ".lancedb")])
    assert completed.returncode == 0
    assert "Header" in completed.stdout
    assert "Indexed Nodes Table" in completed.stdout
    assert "Graph Stats Table" in completed.stdout
    assert "Vector DB Panel" in completed.stdout


def test_inspect_empty_valid_index_exits_zero(tmp_path: Path) -> None:
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=_FakeEmbeddingProvider())
    store.rebuild_index([])
    completed = _run_inspect(["--db-dir", str(tmp_path / ".lancedb")])
    assert completed.returncode == 0
    assert "row_count" in completed.stdout
    assert "0" in completed.stdout


def test_inspect_missing_or_invalid_db_dir_exits_non_zero(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing.lancedb"
    completed = _run_inspect(["--db-dir", str(missing_db)])
    assert completed.returncode != 0
    assert "Missing or invalid index" in completed.stdout


def test_inspect_graph_rebuild_failure_still_shows_vector_data(tmp_path: Path) -> None:
    store = SkeletonNodeVectorStore(db_dir=tmp_path / ".lancedb", embedding_provider=_FakeEmbeddingProvider())
    store.rebuild_index(
        [
            SkeletonNode("a.py", 1, 2, "def alpha():\n    beta()", "docs"),
            SkeletonNode("b.py", 1, 2, "def beta():\n    alpha()", "docs"),
        ]
    )
    completed = _run_inspect(["--db-dir", str(tmp_path / ".lancedb")])
    assert completed.returncode == 0
    assert "graph_source=unavailable" in completed.stdout
    assert "Vector DB Panel" in completed.stdout
