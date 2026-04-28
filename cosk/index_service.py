from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Literal, Protocol

from cosk.config import CoskConfig, get_cosk_config
from cosk.extraction.models import SkeletonNode
from cosk.extraction.parser import _iter_supported_files, extract_file_skeleton_nodes
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


@dataclass(slots=True, frozen=True)
class IndexIssue:
    kind: str
    path: str
    message: str


class IndexProgressObserver(Protocol):
    def start(self, mode: str, total_files: int, deleted_files: int = 0) -> None: ...

    def advance(self, file_path: Path, extracted_nodes: int, skipped: bool = False) -> None: ...

    def record_issue(self, issue: IndexIssue) -> None: ...

    def finish(self, result: "IndexSyncResult", elapsed_seconds: float, issue_summary: dict[str, int]) -> None: ...


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
    processed_files: int = 0
    skipped_files: int = 0
    elapsed_seconds: float = 0.0
    issue_counts: dict[str, int] = field(default_factory=dict)


def _resolve_db_dir(request: IndexBuildRequest) -> Path:
    if request.db_dir is not None:
        return request.db_dir
    return request.target_dir / ".lancedb"


def _collect_issues(
    issues: list[IndexIssue],
    observer: IndexProgressObserver | None,
    kind: str,
    file_path: Path,
    message: str,
) -> None:
    issue = IndexIssue(kind=kind, path=file_path.resolve().as_posix(), message=message)
    issues.append(issue)
    if observer is not None:
        observer.record_issue(issue)


def _summarize_issues(issues: list[IndexIssue]) -> tuple[int, dict[str, int]]:
    if not issues:
        return 0, {}
    per_file = {issue.path for issue in issues}
    per_kind = dict(Counter(issue.kind for issue in issues))
    return len(per_file), per_kind


def _run_extraction(
    *,
    files: list[Path],
    config: CoskConfig,
    observer: IndexProgressObserver | None,
) -> tuple[list[SkeletonNode], list[IndexIssue]]:
    nodes: list[SkeletonNode] = []
    issues: list[IndexIssue] = []
    for file_path in files:
        before = len(issues)
        extracted = extract_file_skeleton_nodes(
            file_path,
            config=config,
            issue_collector=lambda kind, path, message: _collect_issues(issues, observer, kind, path, message),
        )
        after = len(issues)
        nodes.extend(extracted)
        if observer is not None:
            observer.advance(file_path, len(extracted), skipped=(after - before) > 0)
    return nodes, issues


def _make_embed_callback(observer: IndexProgressObserver | None) -> Callable[[int, int], None] | None:
    """Build an embedding progress callback if the observer supports it."""
    if observer is None or not hasattr(observer, "embed_start") or not hasattr(observer, "embed_advance"):
        return None

    def callback(current: int, total: int) -> None:
        if current == 1:
            observer.embed_start(total)  # type: ignore[union-attr]
        observer.embed_advance(current, total)  # type: ignore[union-attr]

    return callback


def _full_sync(
    request: IndexBuildRequest,
    vector_store: SkeletonNodeVectorStore,
    index_name: str,
    *,
    mode: Literal["full", "incremental_fallback_full"] = "full",
    warnings: list[str] | None = None,
    progress_observer: IndexProgressObserver | None = None,
) -> IndexSyncResult:
    db_dir = _resolve_db_dir(request)
    config = request.config or get_cosk_config()
    supported_files = _iter_supported_files(request.target_dir, config)
    if progress_observer is not None:
        progress_observer.start(mode, len(supported_files), 0)
    nodes, issues = _run_extraction(files=supported_files, config=config, observer=progress_observer)
    vector_store.rebuild_index(nodes, on_node_embedded=_make_embed_callback(progress_observer))
    rebuild(nodes)
    current_snapshot = snapshot_files(request.target_dir, config)
    manifest = build_manifest(request.target_dir, config, current_snapshot)
    save_manifest(db_dir, manifest)
    upsert_index(
        index_name,
        request.target_dir,
        db_dir,
        last_indexed_at=manifest.last_indexed_at,
    )
    skipped_files, issue_counts = _summarize_issues(issues)
    return IndexSyncResult(
        mode=mode,
        index_name=index_name,
        target_dir=request.target_dir.resolve().as_posix(),
        db_dir=db_dir.resolve().as_posix(),
        added_files=len(current_snapshot),
        updated_files=0,
        deleted_files=0,
        indexed_nodes=len(nodes),
        warnings=warnings or [],
        processed_files=len(supported_files),
        skipped_files=skipped_files,
        issue_counts=issue_counts,
    )


def sync_index(
    request: IndexBuildRequest,
    embedding_provider: object,
    *,
    progress_observer: IndexProgressObserver | None = None,
) -> IndexSyncResult:
    started = perf_counter()
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
    index_name = request.name or "default"

    if not request.incremental:
        result = _full_sync(request, vector_store, index_name, progress_observer=progress_observer)
        result.elapsed_seconds = perf_counter() - started
        if progress_observer is not None:
            progress_observer.finish(result, result.elapsed_seconds, result.issue_counts)
        return result

    warnings: list[str] = []
    try:
        manifest = load_manifest(request.db_dir)
    except ManifestError as exc:
        warnings.append(str(exc))
        manifest = None

    if not vector_store.validate_index() or manifest is None:
        warnings.append("Incremental index unavailable; ran full indexing.")
        result = _full_sync(
            request,
            vector_store,
            index_name,
            mode="incremental_fallback_full",
            warnings=warnings,
            progress_observer=progress_observer,
        )
        result.elapsed_seconds = perf_counter() - started
        if progress_observer is not None:
            progress_observer.finish(result, result.elapsed_seconds, result.issue_counts)
        return result

    if manifest.target_dir != request.target_dir.resolve().as_posix():
        warnings.append("Manifest target directory mismatch; ran full indexing.")
        result = _full_sync(
            request,
            vector_store,
            index_name,
            mode="incremental_fallback_full",
            warnings=warnings,
            progress_observer=progress_observer,
        )
        result.elapsed_seconds = perf_counter() - started
        if progress_observer is not None:
            progress_observer.finish(result, result.elapsed_seconds, result.issue_counts)
        return result

    current_snapshot = snapshot_files(request.target_dir, config)
    added, updated, deleted = diff_manifest(manifest.files, current_snapshot)
    changed = added + updated
    if progress_observer is not None:
        progress_observer.start("incremental", len(changed), len(deleted))

    delete_paths = [(request.target_dir / relative_path).resolve().as_posix() for relative_path in (*updated, *deleted)]
    if delete_paths:
        vector_store.delete_by_file_paths(delete_paths)

    nodes_to_upsert, issues = _run_extraction(
        files=[request.target_dir / relative_path for relative_path in changed],
        config=config,
        observer=progress_observer,
    )
    if nodes_to_upsert:
        vector_store.upsert_nodes(nodes_to_upsert, on_node_embedded=_make_embed_callback(progress_observer))

    current_nodes = vector_store.load_all_nodes()
    rebuild(current_nodes)

    new_manifest = build_manifest(request.target_dir, config, current_snapshot)
    save_manifest(request.db_dir, new_manifest)
    upsert_index(index_name, request.target_dir, request.db_dir, last_indexed_at=new_manifest.last_indexed_at)

    skipped_files, issue_counts = _summarize_issues(issues)
    result = IndexSyncResult(
        mode="incremental",
        index_name=index_name,
        target_dir=request.target_dir.resolve().as_posix(),
        db_dir=request.db_dir.resolve().as_posix(),
        added_files=len(added),
        updated_files=len(updated),
        deleted_files=len(deleted),
        indexed_nodes=len(nodes_to_upsert),
        warnings=warnings,
        processed_files=len(changed),
        skipped_files=skipped_files,
        issue_counts=issue_counts,
        elapsed_seconds=perf_counter() - started,
    )
    if progress_observer is not None:
        progress_observer.finish(result, result.elapsed_seconds, issue_counts)
    return result
