from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cosk.config import CoskConfig, get_cosk_config
from cosk.extraction.models import SkeletonNode
from cosk.extraction.parser import extract_file_skeleton_nodes, extract_skeleton_nodes
from cosk.graph.builder import rebuild
from cosk.index_manifest import (
    ManifestError,
    build_manifest,
    diff_manifest,
    load_manifest,
    save_manifest,
    snapshot_files,
)
from cosk.indexing.vector_store import SkeletonNodeVectorStore
from cosk.repo_registry import upsert_index


@dataclass(slots=True)
class IndexBuildRequest:
    name: str | None
    target_dir: Path
    db_dir: Path | None = None
    incremental: bool = False
    config: CoskConfig | None = None


@dataclass(slots=True)
class IndexSyncResult:
    mode: Literal["full", "incremental", "incremental_fallback_full"]
    index_name: str
    target_dir: str
    db_dir: str
    added_files: int
    updated_files: int
    deleted_files: int
    indexed_nodes: int
    warnings: list[str] = field(default_factory=list)


def _resolve_db_dir(request: IndexBuildRequest) -> Path:
    if request.db_dir is not None:
        return request.db_dir
    return request.target_dir / ".lancedb"


def _full_sync(
    request: IndexBuildRequest,
    vector_store: SkeletonNodeVectorStore,
    *,
    mode: Literal["full", "incremental_fallback_full"] = "full",
    warnings: list[str] | None = None,
) -> IndexSyncResult:
    config = request.config or get_cosk_config()
    nodes = extract_skeleton_nodes(request.target_dir, config=config)
    vector_store.rebuild_index(nodes)
    rebuild(nodes)
    current_snapshot = snapshot_files(request.target_dir, config)
    manifest = build_manifest(request.target_dir, config, current_snapshot)
    save_manifest(_resolve_db_dir(request), manifest)
    index_name = request.name or "default"
    upsert_index(
        index_name,
        request.target_dir,
        _resolve_db_dir(request),
        last_indexed_at=manifest.last_indexed_at,
    )
    return IndexSyncResult(
        mode=mode,
        index_name=index_name,
        target_dir=request.target_dir.resolve().as_posix(),
        db_dir=_resolve_db_dir(request).resolve().as_posix(),
        added_files=len(current_snapshot),
        updated_files=0,
        deleted_files=0,
        indexed_nodes=len(nodes),
        warnings=warnings or [],
    )


def sync_index(request: IndexBuildRequest, embedding_provider: object) -> IndexSyncResult:
    config = request.config or get_cosk_config()
    request = IndexBuildRequest(
        name=request.name,
        target_dir=request.target_dir,
        db_dir=_resolve_db_dir(request),
        incremental=request.incremental,
        config=config,
    )
    if not request.target_dir.exists() or not request.target_dir.is_dir():
        raise ValueError(f"Target directory does not exist or is not a directory: '{request.target_dir}'.")
    vector_store = SkeletonNodeVectorStore(db_dir=request.db_dir, embedding_provider=embedding_provider)

    if not request.incremental:
        return _full_sync(request, vector_store)

    warnings: list[str] = []
    try:
        manifest = load_manifest(request.db_dir)
    except ManifestError as exc:
        warnings.append(str(exc))
        manifest = None

    if not vector_store.validate_index() or manifest is None:
        warnings.append("Incremental index unavailable; ran full indexing.")
        return _full_sync(request, vector_store, mode="incremental_fallback_full", warnings=warnings)

    if manifest.target_dir != request.target_dir.resolve().as_posix():
        warnings.append("Manifest target directory mismatch; ran full indexing.")
        return _full_sync(request, vector_store, mode="incremental_fallback_full", warnings=warnings)

    current_snapshot = snapshot_files(request.target_dir, config)
    added, updated, deleted = diff_manifest(manifest.files, current_snapshot)
    changed = added + updated

    delete_paths = [(request.target_dir / relative_path).resolve().as_posix() for relative_path in (*updated, *deleted)]
    if delete_paths:
        vector_store.delete_by_file_paths(delete_paths)

    nodes_to_upsert: list[SkeletonNode] = []
    for relative_path in changed:
        file_path = request.target_dir / relative_path
        nodes_to_upsert.extend(extract_file_skeleton_nodes(file_path, config=config))
    if nodes_to_upsert:
        vector_store.upsert_nodes(nodes_to_upsert)

    current_nodes = vector_store.load_all_nodes()
    rebuild(current_nodes)

    new_manifest = build_manifest(request.target_dir, config, current_snapshot)
    save_manifest(request.db_dir, new_manifest)
    index_name = request.name or "default"
    upsert_index(index_name, request.target_dir, request.db_dir, last_indexed_at=new_manifest.last_indexed_at)

    return IndexSyncResult(
        mode="incremental",
        index_name=index_name,
        target_dir=request.target_dir.resolve().as_posix(),
        db_dir=request.db_dir.resolve().as_posix(),
        added_files=len(added),
        updated_files=len(updated),
        deleted_files=len(deleted),
        indexed_nodes=len(nodes_to_upsert),
        warnings=warnings,
    )

