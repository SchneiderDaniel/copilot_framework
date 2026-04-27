from __future__ import annotations

import json

import pytest

from cosk.index_manifest import ManifestError, diff_manifest, load_manifest, save_manifest


def test_manifest_roundtrip(tmp_path) -> None:
    db_dir = tmp_path / ".lancedb"
    db_dir.mkdir()
    manifest = {
        "version": 1,
        "target_dir": tmp_path.as_posix(),
        "respect_gitignore": True,
        "last_indexed_at": "now",
        "files": {"a.py": {"mtime_ns": 1}},
    }
    (db_dir / "cosk.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loaded = load_manifest(db_dir)
    assert loaded is not None
    save_manifest(db_dir, loaded)
    assert load_manifest(db_dir) is not None


def test_manifest_corrupt_raises(tmp_path) -> None:
    db_dir = tmp_path / ".lancedb"
    db_dir.mkdir()
    (db_dir / "cosk.manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(db_dir)


def test_diff_manifest_added_updated_deleted() -> None:
    previous = {"a.py": {"mtime_ns": 1}, "gone.py": {"mtime_ns": 1}}
    current = {"a.py": 2, "new.py": 1}
    added, updated, deleted = diff_manifest(previous, current)
    assert added == ["new.py"]
    assert updated == ["a.py"]
    assert deleted == ["gone.py"]

