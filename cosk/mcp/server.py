"""cosk MCP server — exposes tools over MCP stdio protocol.

Usage:
  python -m cosk.mcp.server
  python -m cosk.mcp.server --target-dir <path>
  python -m cosk.mcp.server --target-dir <path> --db-dir <db_path>
  python -m cosk.mcp.server --db-dir <db_path>

Arguments:
  --target-dir    Directory to extract and index on startup (full rebuild).
  --db-dir        LanceDB directory path.

Error Behaviors:
  Startup: startup failures abort with non-zero exit and stderr message.
  Tool: blank query returns INVALID_PARAMS; runtime errors return INTERNAL_ERROR.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import json
import os
from pathlib import Path
import sys
from typing import Any

from cosk.config import TopKValidationError, get_cosk_config, resolve_top_k
from cosk.graph import state
from cosk.index_manager import IndexManager
from cosk.index_service import IndexBuildRequest
from cosk.indexing.embedding import GeminiEmbeddingProvider
from cosk.indexing.vector_store import SkeletonNodeVectorStore
from cosk.safety.middleware import (
    record_source_retrieval,
    record_search_origin,
    safety_wrap_get_neighbors,
)
from cosk.token_estimation import estimate_with_warnings


def _load_mcp_sdk_modules() -> tuple[Any, Any, Any, Any]:
    package_root = Path(__file__).resolve().parents[1]
    removed_paths: list[tuple[int, str]] = []
    for index, path in enumerate(list(sys.path)):
        resolved = Path(path or os.getcwd()).resolve()
        if resolved == package_root:
            removed_paths.append((index, path))
    for _, path in removed_paths:
        while path in sys.path:
            sys.path.remove(path)
    existing_module = sys.modules.get("mcp")
    if existing_module is not None:
        module_file = getattr(existing_module, "__file__", "")
        if module_file and Path(module_file).resolve().parent == package_root / "mcp":
            for module_name in [name for name in list(sys.modules) if name == "mcp" or name.startswith("mcp.")]:
                del sys.modules[module_name]
    try:
        import mcp.types as loaded_types
        from mcp.server.fastmcp import Context as loaded_context
        from mcp.server.fastmcp import FastMCP as loaded_fast_mcp
        from mcp.shared.exceptions import McpError as loaded_mcp_error
    finally:
        for index, path in sorted(removed_paths, key=lambda item: item[0]):
            sys.path.insert(index, path)
    return loaded_types, loaded_fast_mcp, loaded_mcp_error, loaded_context


mcp_types, FastMCP, McpError, Context = _load_mcp_sdk_modules()
DEFAULT_DB_DIR = Path(__file__).resolve().parents[1] / ".lancedb"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run cosk MCP server over stdio transport.")
    parser.add_argument("--target-dir", type=Path, default=None, help="Directory to extract and index on startup.")
    parser.add_argument("--db-dir", type=Path, default=DEFAULT_DB_DIR, help="LanceDB directory path.")
    parser.add_argument("--index-name", type=str, default=None, help="Named index to load from registry.")
    return parser.parse_args(argv)


def load_embedding_provider() -> Any:
    provider_factory = os.getenv("COSK_EMBEDDING_PROVIDER_FACTORY")
    if not provider_factory:
        return GeminiEmbeddingProvider()
    if ":" not in provider_factory:
        raise SystemExit("Invalid COSK_EMBEDDING_PROVIDER_FACTORY format. Expected 'module:callable'.")
    module_name, factory_name = provider_factory.split(":", maxsplit=1)
    try:
        module = import_module(module_name)
        provider = getattr(module, factory_name)()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to load embedding provider factory '{provider_factory}': {exc}") from exc
    if not hasattr(provider, "embed") or not callable(provider.embed):
        raise SystemExit("Embedding provider must define an embed(text: str) method.")
    return provider


def validate_and_load_index(db_dir: Path, embedding_provider: Any) -> SkeletonNodeVectorStore:
    vector_store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=embedding_provider)
    if not vector_store.validate_index():
        raise SystemExit(f"Existing index missing or invalid at '{db_dir}'.")
    return vector_store


def build_index_from_target(
    target_dir: Path,
    db_dir: Path,
    embedding_provider: Any,
    *,
    config=None,
) -> SkeletonNodeVectorStore:
    manager = IndexManager(
        embedding_provider=embedding_provider,
        config=config or get_cosk_config(),
        default_db_dir=db_dir,
    )
    manager.sync(
        IndexBuildRequest(
            name="default",
            target_dir=target_dir,
            db_dir=db_dir,
            incremental=False,
            config=manager.config,
        )
    )
    return manager.get_context(db_dir=db_dir).vector_store


def _node_graph_id(row: dict[str, object]) -> str:
    return f"{row['file_path']}:{row['start_line']}"


def _effective_summary(raw_signature: object, summary: object) -> str:
    summary_text = str(summary or "").strip()
    if summary_text:
        return summary_text
    return str(raw_signature or "").strip()


def _filter_token_warnings(warnings: list[str]) -> list[str]:
    return [warning for warning in warnings if "tiktoken" not in warning.lower()]


def enrich_search_results(results: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    enriched: list[dict[str, object]] = []
    for row in results:
        summary = _effective_summary(row.get("raw_signature", ""), row.get("summary", ""))
        graph_node_id = _node_graph_id(row)
        token_count, token_warnings = estimate_with_warnings(f"{row.get('raw_signature', '')}\n{summary}")
        warnings.extend(_filter_token_warnings(token_warnings))
        enriched.append({**row, "summary": summary, "graph_node_id": graph_node_id, "token_count": token_count})
    return enriched, sorted(set(warnings))


def enrich_neighbor_entries(
    vector_store: SkeletonNodeVectorStore, neighbor_map: dict[str, list[dict[str, object]]]
) -> tuple[dict[str, list[dict[str, object]]], list[str]]:
    ids = [entry["node_id"] for entry in (neighbor_map.get("inbound", []) + neighbor_map.get("outbound", []))]
    details = vector_store.get_node_details(ids)
    warnings: list[str] = []
    enriched = {"inbound": [], "outbound": []}
    for direction in ("inbound", "outbound"):
        for entry in neighbor_map.get(direction, []):
            detail = details.get(entry["node_id"], {})
            summary = _effective_summary(detail.get("raw_signature", ""), detail.get("summary", ""))
            text = f"{detail.get('raw_signature', '')}\n{summary}"
            token_count, token_warnings = estimate_with_warnings(text)
            warnings.extend(_filter_token_warnings(token_warnings))
            enriched[direction].append({**entry, "summary": summary, "token_count": token_count})
    return enriched, sorted(set(warnings))


def _resolve_context_target_dir(context: Any | None) -> Path | None:
    if context is None:
        return None
    target_dir = getattr(context, "target_dir", None)
    if target_dir is not None:
        return Path(target_dir)
    manifest = getattr(context, "manifest", None)
    manifest_target_dir = getattr(manifest, "target_dir", None)
    if manifest_target_dir is not None:
        return Path(manifest_target_dir)
    return None


def _resolve_source_path(file_path: str, context_target_dir: Path | None = None) -> tuple[Path, str | None]:
    path = Path(file_path)
    if context_target_dir is not None and not path.is_absolute():
        path = (context_target_dir / path).resolve()
    if path.is_absolute():
        path = path.resolve()
    if context_target_dir is not None and path.is_absolute():
        root = context_target_dir.resolve()
        if root not in [path, *path.parents]:
            return path, "path is outside indexed root"
    return path, None


def read_file_range(file_path: str, start_line: int, end_line: int, *, context_target_dir: Path | None = None) -> str:
    path, path_error = _resolve_source_path(file_path, context_target_dir)
    if path_error is not None:
        return f"Unable to read '{file_path}': {path_error}"
    try:
        with open(str(path), "r", encoding="utf-8") as source_file:
            lines = source_file.readlines()
    except Exception as exc:  # noqa: BLE001
        return f"Unable to read '{file_path}': {exc}"
    if start_line > len(lines) or end_line > len(lines):
        return f"Requested line range {start_line}-{end_line} is outside file bounds; file has {len(lines)} lines."
    return "".join(lines[start_line - 1 : end_line])


def create_mcp_server(
    vector_store: SkeletonNodeVectorStore | Any | None = None,
    *,
    manager: IndexManager | None = None,
) -> FastMCP:
    mcp = FastMCP("cosk")
    config = manager.config if manager else get_cosk_config()

    def _resolve_context(index_name: str | None = None):
        if manager is not None:
            return manager.get_context(index_name=index_name)
        if vector_store is None:
            raise RuntimeError("No vector store loaded")
        return None

    def _resolve_store(index_name: str | None = None):
        context = _resolve_context(index_name)
        return context.vector_store if context is not None else vector_store

    def _hybrid_rrf_merge(
        bm25_results: list[dict[str, object]],
        vector_results: list[dict[str, object]],
        *,
        top_k: int,
        rrf_k: int = 60,
    ) -> list[dict[str, object]]:
        scores: dict[str, float] = {}
        payloads: dict[str, dict[str, object]] = {}

        for rank, row in enumerate(bm25_results, start=1):
            node_id = str(row.get("node_id", ""))
            if not node_id:
                continue
            payloads.setdefault(node_id, row)
            scores[node_id] = scores.get(node_id, 0.0) + (1.0 / (rrf_k + rank))

        for rank, row in enumerate(vector_results, start=1):
            node_id = str(row.get("node_id", ""))
            if not node_id:
                continue
            payloads.setdefault(node_id, row)
            scores[node_id] = scores.get(node_id, 0.0) + (1.0 / (rrf_k + rank))

        ranked_node_ids = sorted(scores.keys(), key=lambda node_id: scores[node_id], reverse=True)
        return [payloads[node_id] for node_id in ranked_node_ids[:top_k]]

    @mcp.tool()
    def cosk_semantic_search(
        query_string: str,
        top_k: int | None = None,
        index_name: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        if not query_string or not query_string.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="query_string must not be blank"))
        try:
            resolved_top_k, warnings = resolve_top_k(top_k, config)
        except TopKValidationError as exc:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message=str(exc))) from exc
        try:
            results = _resolve_store(index_name).search(query_string.strip(), top_k=resolved_top_k)
            enriched, token_warnings = enrich_search_results(results)
            record_search_origin(ctx, enriched)
            if ctx is not None and hasattr(ctx, "info"):
                for warning in [*warnings, *token_warnings]:
                    ctx.info(warning)
            return json.dumps(enriched)
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_semantic_search failed: {exc}")
            ) from exc

    @mcp.tool()
    def cosk_search_by_name(
        query: str,
        kind: str = "any",
        index_name: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        if not query or not query.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="query must not be blank"))
        normalized_kind = kind.strip().lower()
        if normalized_kind not in {"function", "class", "method", "any"}:
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="kind must be one of: function, class, method, any")
            )
        try:
            results = _resolve_store(index_name).search_by_name(query.strip(), kind=normalized_kind)
            enriched, token_warnings = enrich_search_results(results)
            record_search_origin(ctx, enriched)
            if ctx is not None and hasattr(ctx, "info"):
                for warning in token_warnings:
                    ctx.info(warning)
            return json.dumps(enriched)
        except ValueError as exc:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message=str(exc))) from exc
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_search_by_name failed: {exc}")
            ) from exc

    @mcp.tool()
    def cosk_symbol_search(
        symbol_name: str,
        top_k: int | None = None,
        fuzzy: bool = False,
        distance: int = 0,
        index_name: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        if not symbol_name or not symbol_name.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="symbol_name must not be blank"))
        if distance < 0:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="distance must be >= 0"))
        try:
            resolved_top_k, warnings = resolve_top_k(top_k, config)
        except TopKValidationError as exc:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message=str(exc))) from exc

        try:
            results = _resolve_store(index_name).search_symbol(
                symbol_name.strip(),
                resolved_top_k,
                fuzzy=fuzzy,
                distance=distance,
            )
            enriched, token_warnings = enrich_search_results(results)
            record_search_origin(ctx, enriched)
            if ctx is not None and hasattr(ctx, "info"):
                for warning in [*warnings, *token_warnings]:
                    ctx.info(warning)
            return json.dumps(enriched)
        except ValueError as exc:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message=str(exc))) from exc
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_symbol_search failed: {exc}")
            ) from exc

    @mcp.tool()
    def cosk_hybrid_search(
        query: str,
        top_k: int | None = None,
        index_name: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        if not query or not query.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="query must not be blank"))
        try:
            resolved_top_k, warnings = resolve_top_k(top_k, config)
        except TopKValidationError as exc:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message=str(exc))) from exc

        normalized_query = query.strip()
        try:
            store = _resolve_store(index_name)
            with ThreadPoolExecutor(max_workers=2) as executor:
                vector_future = executor.submit(store.search, normalized_query, top_k=resolved_top_k)
                bm25_future = executor.submit(store.search_symbol, normalized_query, resolved_top_k, fuzzy=False)
                vector_results = vector_future.result()
                bm25_results = bm25_future.result()
            merged = _hybrid_rrf_merge(bm25_results, vector_results, top_k=resolved_top_k)
            enriched, token_warnings = enrich_search_results(merged)
            record_search_origin(ctx, enriched)
            if ctx is not None and hasattr(ctx, "info"):
                for warning in [*warnings, *token_warnings]:
                    ctx.info(warning)
            return json.dumps(enriched)
        except ValueError as exc:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message=str(exc))) from exc
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_hybrid_search failed: {exc}")
            ) from exc

    def _core_get_neighbors(node_id: str, index_name: str | None) -> str:
        if manager is not None:
            context = manager.get_context(index_name=index_name)
            graph = context.graph
            store = context.vector_store
        else:
            graph = state.get_graph()
            store = vector_store
        if graph is None:
            raise McpError(
                mcp_types.ErrorData(
                    code=mcp_types.INTERNAL_ERROR,
                    message="cosk_get_neighbors failed: relationship graph is not loaded",
                )
            )
        neighbors = graph.get_neighbors(node_id)
        enriched, _warnings = enrich_neighbor_entries(store, neighbors)
        return json.dumps(enriched)

    @mcp.tool()
    def cosk_get_neighbors(node_id: str, index_name: str | None = None, ctx: Context | None = None) -> str:
        if not node_id or not node_id.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="node_id must not be blank"))
        try:
            return safety_wrap_get_neighbors(
                node_id.strip(),
                ctx,
                lambda n: _core_get_neighbors(n, index_name),
                state.get_graph(),
            )
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_get_neighbors failed: {exc}")
            ) from exc

    @mcp.tool()
    def cosk_get_symbol_source(
        node_ids: list[str],
        index_name: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        if not isinstance(node_ids, list) or not node_ids:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="node_ids must be a non-empty list"))
        try:
            context = _resolve_context(index_name)
            context_target_dir = _resolve_context_target_dir(context)
            details_map = _resolve_store(index_name).get_node_details(node_ids)
            entries: list[dict[str, object]] = []
            for node_id in node_ids:
                detail = details_map.get(node_id)
                if detail is None:
                    entries.append({"node_id": node_id, "error": "not found"})
                    continue
                file_path = detail.get("file_path")
                start_line = detail.get("start_line")
                end_line = detail.get("end_line")
                if not file_path or start_line is None or end_line is None:
                    entries.append({"node_id": node_id, "error": "metadata is incomplete"})
                    continue
                path, path_error = _resolve_source_path(str(file_path), context_target_dir)
                if path_error is not None:
                    entries.append({"node_id": node_id, "error": path_error})
                    continue
                source_code = read_file_range(str(path), int(start_line), int(end_line), context_target_dir=None)
                if source_code.startswith("Unable to read '") or source_code.startswith("Requested line range "):
                    entries.append({"node_id": node_id, "error": source_code})
                    continue
                token_count, _warnings = estimate_with_warnings(source_code)
                entries.append(
                    {
                        "node_id": node_id,
                        "file_path": str(file_path),
                        "start_line": int(start_line),
                        "end_line": int(end_line),
                        "raw_signature": str(detail.get("raw_signature", "")),
                        "source_code": source_code,
                        "token_count": token_count,
                    }
                )
            record_source_retrieval(ctx)
            return json.dumps(entries)
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_get_symbol_source failed: {exc}")
            ) from exc

    @mcp.tool()
    def cosk_find_usage(entity_name: str, index_name: str | None = None) -> str:
        if not entity_name or not entity_name.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="entity_name must not be blank"))
        try:
            graph = manager.get_context(index_name=index_name).graph if manager is not None else state.get_graph()
            if graph is None:
                raise McpError(
                    mcp_types.ErrorData(
                        code=mcp_types.INTERNAL_ERROR,
                        message="cosk_find_usage failed: relationship graph is not loaded",
                    )
                )
            return json.dumps(graph.find_usages(entity_name.strip()))
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_find_usage failed: {exc}")) from exc

    return mcp


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        embedding_provider = load_embedding_provider()
        manager = IndexManager(
            embedding_provider=embedding_provider,
            config=get_cosk_config(),
            default_db_dir=args.db_dir,
        )
        if args.target_dir is not None:
            manager.sync(
                IndexBuildRequest(
                    name=args.index_name or "default",
                    target_dir=args.target_dir,
                    db_dir=args.db_dir,
                    incremental=False,
                    config=manager.config,
                )
            )
        else:
            manager.get_context(index_name=args.index_name, db_dir=args.db_dir)
        create_mcp_server(manager=manager).run("stdio")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()

