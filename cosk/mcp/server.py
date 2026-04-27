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
    record_expand_definition,
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


def enrich_search_results(results: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    enriched: list[dict[str, object]] = []
    for row in results:
        graph_node_id = _node_graph_id(row)
        token_count, token_warnings = estimate_with_warnings(f"{row.get('raw_signature', '')}\n{row.get('summary', '')}")
        warnings.extend(token_warnings)
        enriched.append({**row, "graph_node_id": graph_node_id, "token_count": token_count})
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
            text = f"{detail.get('raw_signature', '')}\n{detail.get('summary', '')}"
            token_count, token_warnings = estimate_with_warnings(text)
            warnings.extend(token_warnings)
            enriched[direction].append({**entry, "token_count": token_count})
    return enriched, sorted(set(warnings))


def read_file_range(file_path: str, start_line: int, end_line: int, *, context_target_dir: Path | None = None) -> str:
    path = Path(file_path)
    if context_target_dir is not None and not path.is_absolute():
        path = (context_target_dir / path).resolve()
    if context_target_dir is not None and path.is_absolute():
        root = context_target_dir.resolve()
        if root not in [path, *path.parents]:
            return f"Unable to read '{file_path}': path is outside indexed root"
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
    def cosk_expand_definition(
        file_path: str,
        start_line: int,
        end_line: int,
        index_name: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        if not file_path or not file_path.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="file_path must not be blank"))
        if start_line < 1:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="start_line must be >= 1"))
        if end_line < start_line:
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="end_line must be >= start_line"))
        context = manager.get_context(index_name=index_name) if manager is not None else None
        record_expand_definition(ctx)
        return read_file_range(file_path.strip(), start_line, end_line, context_target_dir=context.target_dir if context else None)

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

