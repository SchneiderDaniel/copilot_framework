from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

from cosk.config import CoskConfig
from cosk.extraction.parser import _iter_supported_files


@dataclass(slots=True)
class IndexManifest:
    version: int
    target_dir: str
    respect_gitignore: bool
    last_indexed_at: str
    files: dict[str, dict[str, int]]


class ManifestError(ValueError):
    """Raised when a manifest cannot be parsed."""


def manifest_path(db_dir: Path) -> Path:
    return db_dir / "cosk.manifest.json"


def load_manifest(db_dir: Path) -> IndexManifest | None:
    path = manifest_path(db_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        files_data = data.get("files", {})
        return IndexManifest(
            version=int(data.get("version", 1)),
            target_dir=str(data["target_dir"]),
            respect_gitignore=bool(data.get("respect_gitignore", True)),
            last_indexed_at=str(data.get("last_indexed_at", "")),
            files={str(key): {"mtime_ns": int(value["mtime_ns"])} for key, value in files_data.items()},
        )
    except Exception as exc:  # noqa: BLE001
        raise ManifestError(f"Invalid manifest at '{path}': {exc}") from exc


def save_manifest(db_dir: Path, manifest: IndexManifest) -> None:
    path = manifest_path(db_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": manifest.version,
        "target_dir": manifest.target_dir,
        "respect_gitignore": manifest.respect_gitignore,
        "last_indexed_at": manifest.last_indexed_at,
        "files": manifest.files,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def snapshot_files(target_dir: Path, config: CoskConfig) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for file_path in _iter_supported_files(target_dir, config):
        rel_path = file_path.relative_to(target_dir).as_posix()
        snapshot[rel_path] = file_path.stat().st_mtime_ns
    return snapshot


def diff_manifest(
    previous_files: dict[str, dict[str, int]], current_snapshot: dict[str, int]
) -> tuple[list[str], list[str], list[str]]:
    added = [path for path in current_snapshot if path not in previous_files]
    updated = [
        path
        for path, mtime_ns in current_snapshot.items()
        if path in previous_files and mtime_ns > int(previous_files[path].get("mtime_ns", 0))
    ]
    deleted = [path for path in previous_files if path not in current_snapshot]
    return sorted(added), sorted(updated), sorted(deleted)


def build_manifest(target_dir: Path, config: CoskConfig, snapshot: dict[str, int]) -> IndexManifest:
    files = {path: {"mtime_ns": mtime_ns} for path, mtime_ns in sorted(snapshot.items())}
    return IndexManifest(
        version=1,
        target_dir=target_dir.resolve().as_posix(),
        respect_gitignore=config.extraction.respect_gitignore,
        last_indexed_at=datetime.now(UTC).isoformat(),
        files=files,
    )

