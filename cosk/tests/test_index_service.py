from __future__ import annotations

import hashlib
from pathlib import Path

from cosk.config import _parse_config
from cosk.extraction.parser import extract_file_skeleton_nodes
from cosk.index_manifest import manifest_path
from cosk.index_service import IndexBuildRequest, sync_index


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[0] / 255.0, digest[1] / 255.0]


def _write_py(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_incremental_index_add_update_delete_cycle(tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.mkdir()
    _write_py(target / "a.py", "def a():\n    return 1\n")
    provider = FakeProvider()
    config = _parse_config({"extraction": {"supported_languages": [{"name": "python", "extensions": [".py"], "grammar_package": "tree_sitter_python", "grammar_module": "language", "query_file": "python.scm"}]}})
    full = sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=tmp_path / ".lancedb", config=config), provider)
    assert full.mode == "full"
    _write_py(target / "a.py", "def a():\n    return 2\n")
    _write_py(target / "b.py", "def b():\n    return 3\n")
    (target / "to_delete.py").write_text("def c():\n    return 4\n", encoding="utf-8")
    sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=tmp_path / ".lancedb", config=config), provider)
    (target / "to_delete.py").unlink()
    incremental = sync_index(
        IndexBuildRequest(name="default", target_dir=target, db_dir=tmp_path / ".lancedb", incremental=True, config=config),
        provider,
    )
    assert incremental.mode in {"incremental", "incremental_fallback_full"}


def test_incremental_does_not_reembed_unchanged_files(tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.mkdir()
    file_a = target / "a.py"
    file_b = target / "b.py"
    _write_py(file_a, "def a():\n    return 1\n")
    _write_py(file_b, "def b():\n    return 2\n")
    provider = FakeProvider()
    config = _parse_config({"extraction": {"supported_languages": [{"name": "python", "extensions": [".py"], "grammar_package": "tree_sitter_python", "grammar_module": "language", "query_file": "python.scm"}]}})
    db_dir = tmp_path / ".lancedb"
    sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=db_dir, config=config), provider)
    baseline_calls = provider.calls
    _write_py(file_a, "def a():\n    return 99\n")
    expected_changed_nodes = len(extract_file_skeleton_nodes(file_a, config=config))

    sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=db_dir, incremental=True, config=config), provider)

    assert provider.calls - baseline_calls == expected_changed_nodes


def test_incremental_no_change_returns_zero_counts(tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.mkdir()
    _write_py(target / "a.py", "def a():\n    return 1\n")
    provider = FakeProvider()
    config = _parse_config({"extraction": {"supported_languages": [{"name": "python", "extensions": [".py"], "grammar_package": "tree_sitter_python", "grammar_module": "language", "query_file": "python.scm"}]}})
    db_dir = tmp_path / ".lancedb"
    sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=db_dir, config=config), provider)
    baseline_calls = provider.calls

    result = sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=db_dir, incremental=True, config=config), provider)

    assert result.mode == "incremental"
    assert result.added_files == 0
    assert result.updated_files == 0
    assert result.deleted_files == 0
    assert result.indexed_nodes == 0
    assert provider.calls == baseline_calls


def test_incremental_missing_manifest_falls_back_to_full(tmp_path: Path) -> None:
    target = tmp_path / "src"
    target.mkdir()
    _write_py(target / "a.py", "def a():\n    return 1\n")
    provider = FakeProvider()
    config = _parse_config({"extraction": {"supported_languages": [{"name": "python", "extensions": [".py"], "grammar_package": "tree_sitter_python", "grammar_module": "language", "query_file": "python.scm"}]}})
    db_dir = tmp_path / ".lancedb"
    sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=db_dir, config=config), provider)
    manifest_path(db_dir).unlink()

    result = sync_index(IndexBuildRequest(name="default", target_dir=target, db_dir=db_dir, incremental=True, config=config), provider)

    assert result.mode == "incremental_fallback_full"
    assert any("Incremental index unavailable" in warning for warning in result.warnings)

