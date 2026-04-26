"""cosk MCP server — exposes cosk_semantic_search over the MCP stdio protocol.

Usage:
  python -m cosk.mcp.server
  python -m cosk.mcp.server --target-dir <path>
  python -m cosk.mcp.server --target-dir <path> --db-dir <db_path>
  python -m cosk.mcp.server --db-dir <db_path>

Arguments:
  --target-dir    Directory to extract and index on startup (full rebuild).
                  If not provided, loads existing index from --db-dir.
  --db-dir        LanceDB directory path. Default: cosk/.lancedb (package root).

Environment:
  COSK_EMBEDDING_PROVIDER_FACTORY   Module:callable to build embedding provider
                                    (e.g. for testing: mymodule:make_provider).
                                    Default: GeminiEmbeddingProvider.

Error Behaviors:
  Startup:  Any failure aborts the process with non-zero exit and stderr message.
  Tool:     Blank/whitespace query returns MCP tool error (isError=True).
            Empty index returns [].
            Runtime errors return MCP tool error.
"""

from __future__ import annotations

import argparse
from importlib import import_module
import json
import os
from pathlib import Path
import sys
from typing import Any

from cosk.extraction.parser import extract_skeleton_nodes
from cosk.graph import state
from cosk.indexing.embedding import GeminiEmbeddingProvider
from cosk.indexing.vector_store import SkeletonNodeVectorStore
from cosk.safety.middleware import (
    record_expand_definition,
    record_search_origin,
    safety_wrap_get_neighbors,
)


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run cosk MCP server over stdio transport.")
    parser.add_argument("--target-dir", type=Path, default=None, help="Directory to extract and index on startup.")
    parser.add_argument(
        "--db-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".lancedb",
        help="LanceDB directory path.",
    )
    return parser.parse_args(argv)


def _load_embedding_provider() -> Any:
    provider_factory = os.getenv("COSK_EMBEDDING_PROVIDER_FACTORY")
    if not provider_factory:
        return GeminiEmbeddingProvider()

    if ":" not in provider_factory:
        raise SystemExit(
            "Invalid COSK_EMBEDDING_PROVIDER_FACTORY format. Expected 'module:callable'."
        )

    module_name, factory_name = provider_factory.split(":", maxsplit=1)
    try:
        module = import_module(module_name)
        factory = getattr(module, factory_name)
        provider = factory()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to load embedding provider factory '{provider_factory}': {exc}") from exc

    if not hasattr(provider, "embed") or not callable(provider.embed):
        raise SystemExit("Embedding provider must define an embed(text: str) method.")
    return provider


def _validate_and_load_index(db_dir: Path, embedding_provider: Any) -> SkeletonNodeVectorStore:
    vector_store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=embedding_provider)
    if not vector_store.validate_index():
        raise SystemExit(f"Existing index missing or invalid at '{db_dir}'.")
    return vector_store


def _build_index_from_target(target_dir: Path, db_dir: Path, embedding_provider: Any) -> SkeletonNodeVectorStore:
    if not target_dir.exists() or not target_dir.is_dir():
        raise SystemExit(f"Target directory does not exist or is not a directory: '{target_dir}'.")

    vector_store = SkeletonNodeVectorStore(db_dir=db_dir, embedding_provider=embedding_provider)
    try:
        nodes = extract_skeleton_nodes(target_dir)
        vector_store.rebuild_index(nodes)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to build index from '{target_dir}': {exc}") from exc
    return vector_store


def create_mcp_server(vector_store: SkeletonNodeVectorStore) -> FastMCP:
    mcp = FastMCP("cosk")

    @mcp.tool()
    def cosk_semantic_search(query_string: str, ctx: Context | None = None) -> str:
        if not query_string or not query_string.strip():
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="query_string must not be blank")
            )
        try:
            results = vector_store.search(query_string.strip(), top_k=5)
            record_search_origin(ctx, results)
            return json.dumps(results)
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_semantic_search failed: {exc}")
            ) from exc

    def _core_get_neighbors(node_id: str) -> str:
        graph = state.get_graph()
        if graph is None:
            raise McpError(
                mcp_types.ErrorData(
                    code=mcp_types.INTERNAL_ERROR,
                    message="cosk_get_neighbors failed: relationship graph is not loaded",
                )
            )
        return json.dumps(graph.get_neighbors(node_id))

    @mcp.tool()
    def cosk_get_neighbors(node_id: str, ctx: Context | None = None) -> str:
        if not node_id or not node_id.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="node_id must not be blank"))
        try:
            return safety_wrap_get_neighbors(node_id.strip(), ctx, _core_get_neighbors, state.get_graph())
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_get_neighbors failed: {exc}")
            ) from exc

    @mcp.tool()
    def cosk_expand_definition(
        file_path: str, start_line: int, end_line: int, ctx: Context | None = None
    ) -> str:
        if not file_path or not file_path.strip():
            raise McpError(mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="file_path must not be blank"))
        if start_line < 1:
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="start_line must be >= 1")
            )
        if end_line < start_line:
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="end_line must be >= start_line")
            )
        try:
            with open(file_path, "r", encoding="utf-8") as source_file:
                lines = source_file.readlines()
        except Exception as exc:  # noqa: BLE001
            return f"Unable to read '{file_path}': {exc}"

        if start_line > len(lines) or end_line > len(lines):
            return f"Requested line range {start_line}-{end_line} is outside file bounds; file has {len(lines)} lines."
        record_expand_definition(ctx)
        return "".join(lines[start_line - 1 : end_line])

    @mcp.tool()
    def cosk_find_usage(entity_name: str) -> str:
        if not entity_name or not entity_name.strip():
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INVALID_PARAMS, message="entity_name must not be blank")
            )
        try:
            graph = state.get_graph()
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
            raise McpError(
                mcp_types.ErrorData(code=mcp_types.INTERNAL_ERROR, message=f"cosk_find_usage failed: {exc}")
            ) from exc

    return mcp


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        embedding_provider = _load_embedding_provider()
        if args.target_dir is not None:
            vector_store = _build_index_from_target(args.target_dir, args.db_dir, embedding_provider)
        else:
            vector_store = _validate_and_load_index(args.db_dir, embedding_provider)
        create_mcp_server(vector_store).run("stdio")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
