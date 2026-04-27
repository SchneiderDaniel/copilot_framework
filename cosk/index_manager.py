from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from cosk.config import CoskConfig, get_cosk_config
from cosk.graph.builder import rebuild
from cosk.index_manifest import load_manifest
from cosk.index_service import IndexBuildRequest, IndexSyncResult, sync_index
from cosk.indexing.vector_store import SkeletonNodeVectorStore
from cosk.repo_registry import RegistryError, load_registry, resolve_index


@dataclass(slots=True)
class IndexContext:
    name: str
    target_dir: Path | None
    db_dir: Path
    vector_store: SkeletonNodeVectorStore
    graph: object | None
    manifest: object | None


class IndexManager:
    def __init__(
        self,
        *,
        embedding_provider: object,
        config: CoskConfig | None = None,
        cwd: Path | None = None,
        default_db_dir: Path | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._config = config or get_cosk_config()
        self._cwd = cwd or Path.cwd()
        self._default_db_dir = default_db_dir
        self._contexts: dict[str, IndexContext] = {}
        self._locks: dict[str, Lock] = {}
        self._global_lock = Lock()

    @property
    def config(self) -> CoskConfig:
        return self._config

    def _get_lock(self, key: str) -> Lock:
        with self._global_lock:
            return self._locks.setdefault(key, Lock())

    def _resolve(self, *, index_name: str | None = None, db_dir: Path | None = None) -> tuple[str, Path | None, Path]:
        if db_dir is not None:
            return index_name or "__adhoc__", None, db_dir
        if index_name is None and self._default_db_dir is not None:
            return "default", None, self._default_db_dir
        try:
            name, entry = resolve_index(index_name, self._cwd)
            return name, Path(entry.target_dir), Path(entry.db_dir)
        except RegistryError:
            fallback = self._default_db_dir or (self._cwd / ".lancedb")
            return index_name or "default", None, fallback

    def _cache_key(self, name: str, db_dir: Path) -> str:
        return f"{name}:{db_dir.resolve().as_posix()}"

    def get_context(self, *, index_name: str | None = None, db_dir: Path | None = None) -> IndexContext:
        name, target_dir, resolved_db_dir = self._resolve(index_name=index_name, db_dir=db_dir)
        key = self._cache_key(name, resolved_db_dir)
        lock = self._get_lock(key)
        with lock:
            if key in self._contexts:
                return self._contexts[key]
            vector_store = SkeletonNodeVectorStore(db_dir=resolved_db_dir, embedding_provider=self._embedding_provider)
            if not vector_store.validate_index():
                raise ValueError(f"Existing index missing or invalid at '{resolved_db_dir}'.")
            graph = rebuild(vector_store.load_all_nodes())
            context = IndexContext(
                name=name,
                target_dir=target_dir,
                db_dir=resolved_db_dir,
                vector_store=vector_store,
                graph=graph,
                manifest=load_manifest(resolved_db_dir),
            )
            self._contexts[key] = context
            return context

    def sync(self, request: IndexBuildRequest) -> IndexSyncResult:
        db_dir = request.db_dir or (request.target_dir / ".lancedb")
        name = request.name or "default"
        key = self._cache_key(name, db_dir)
        with self._get_lock(key):
            result = sync_index(request, self._embedding_provider)
            self._contexts.pop(key, None)
            return result

    def list_registry(self) -> dict[str, object]:
        registry = load_registry(self._cwd)
        return {
            "version": registry.version,
            "default": registry.default,
            "indexes": {
                name: {
                    "target_dir": entry.target_dir,
                    "db_dir": entry.db_dir,
                    "last_indexed_at": entry.last_indexed_at,
                }
                for name, entry in registry.indexes.items()
            },
        }

