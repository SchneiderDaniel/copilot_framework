from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

from cosk import inspect
from cosk.cli.output import RichIndexProgressObserver, write_error, write_info, write_json
from cosk.cli.setup_wizard import run_setup_wizard, run_uninstall_wizard
from cosk.config import CoskConfig, TopKValidationError, get_cosk_config, resolve_top_k
from cosk.http_server import run_http_server
from cosk.index_manager import IndexManager
from cosk.index_service import IndexBuildRequest
from cosk.mcp import server
from cosk.repo_registry import load_registry, remove_index, set_default_index
from cosk.watch_mode import run_watch_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cosk CLI for indexing and querying codebase context.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Quick Start:\n"
            "  cosk index --target-dir <repo>\n"
            "  cosk serve --db-dir <repo>/.lancedb\n"
            "  cosk search --query \"find auth middleware\"\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_cli_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Build or update index", description="Build or update index")
    index_parser.add_argument("--target-dir", type=Path, required=True, help="Repository directory to index.")
    index_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    index_parser.add_argument("--name", type=str, default=None, help="Optional registry name for this index.")
    index_parser.add_argument("--incremental", action="store_true", help="Only reindex changed files from the manifest.")
    index_parser.add_argument("--json", action="store_true", help="Force JSON output on stdout.")
    index_parser.add_argument("--no-gitignore", action="store_true", help="Include files normally ignored by .gitignore.")
    index_parser.set_defaults(handler=_run_index)

    search_parser = subparsers.add_parser("search", help="Search indexed skeleton nodes")
    search_parser.add_argument("query", nargs="?")
    search_parser.add_argument("--query", dest="query_flag", default=None)
    search_parser.add_argument("--top-k", type=int, default=None, help="Maximum number of results to return.")
    search_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    search_parser.add_argument("--name", type=str, default=None, help="Registry index name to query.")
    search_parser.set_defaults(handler=_run_search)

    neighbors_parser = subparsers.add_parser("neighbors", help="Get graph neighbors for a node")
    neighbors_parser.add_argument("node_id", nargs="?")
    neighbors_parser.add_argument("--node-id", dest="node_id_flag", default=None)
    neighbors_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    neighbors_parser.add_argument("--name", type=str, default=None, help="Registry index name to query.")
    neighbors_parser.set_defaults(handler=_run_neighbors)

    expand_parser = subparsers.add_parser("expand", help="Expand source lines")
    expand_parser.add_argument("file_path", nargs="?")
    expand_parser.add_argument("start_line", nargs="?", type=int)
    expand_parser.add_argument("end_line", nargs="?", type=int)
    expand_parser.add_argument("--file-path", dest="file_path_flag", default=None)
    expand_parser.add_argument("--start-line", dest="start_line_flag", type=int, default=None)
    expand_parser.add_argument("--end-line", dest="end_line_flag", type=int, default=None)
    expand_parser.add_argument("--name", type=str, default=None, help="Registry index name to query.")
    expand_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    expand_parser.set_defaults(handler=_run_expand)

    usage_parser = subparsers.add_parser("find-usage", help="Find symbol usage")
    usage_parser.add_argument("entity_name", nargs="?")
    usage_parser.add_argument("--entity-name", dest="entity_name_flag", default=None)
    usage_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    usage_parser.add_argument("--name", type=str, default=None, help="Registry index name to query.")
    usage_parser.set_defaults(handler=_run_find_usage)

    watch_parser = subparsers.add_parser("watch", help="Watch filesystem and reindex incrementally")
    watch_parser.add_argument("--target-dir", type=Path, required=True, help="Repository directory to watch.")
    watch_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    watch_parser.add_argument("--name", type=str, default=None, help="Optional registry name for this index.")
    watch_parser.add_argument("--no-gitignore", action="store_true", help="Include files normally ignored by .gitignore.")
    watch_parser.set_defaults(handler=_run_watch)

    serve_parser = subparsers.add_parser("serve", help="Serve MCP or HTTP transport")
    serve_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    serve_parser.add_argument("--index-name", type=str, default=None, help="Registry index name to serve.")
    serve_parser.add_argument("--http", action="store_true", help="Run HTTP mode instead of stdio MCP mode.")
    serve_parser.add_argument("--host", type=str, default=None, help="HTTP host (when --http is enabled).")
    serve_parser.add_argument("--port", type=int, default=None, help="HTTP port (when --http is enabled).")
    serve_parser.set_defaults(handler=_run_serve)

    inspect_parser = subparsers.add_parser("inspect", help="Print local index and graph diagnostics")
    inspect_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    inspect_parser.set_defaults(handler=_run_inspect)

    registry_parser = subparsers.add_parser("registry", help="Manage named index registry")
    registry_subparsers = registry_parser.add_subparsers(dest="registry_command", required=True)
    registry_list = registry_subparsers.add_parser("list", help="List named indexes in registry")
    registry_list.set_defaults(handler=_run_registry_list)
    registry_remove = registry_subparsers.add_parser("remove", help="Remove an index from registry")
    registry_remove.add_argument("--name", required=True)
    registry_remove.set_defaults(handler=_run_registry_remove)
    registry_default = registry_subparsers.add_parser("set-default", help="Set registry default index")
    registry_default.add_argument("--name", required=True)
    registry_default.set_defaults(handler=_run_registry_set_default)

    install_parser = subparsers.add_parser(
        "install",
        help="Index a repo and auto-configure MCP clients (one-shot onboarding)",
        description=(
            "Index a repository and automatically inject the cosk MCP server entry into\n"
            "any detected AI client configs (Claude Desktop, VS Code, Cursor, Windsurf, Zed).\n"
            "Prints a ready-to-paste snippet for CLAUDE.md / agents.md / copilot instructions."
        ),
    )
    install_parser.add_argument("--target-dir", type=Path, default=None, help="Repository to index.")
    install_parser.add_argument("--db-dir", type=Path, default=None, help="Override LanceDB directory path.")
    install_parser.add_argument("--name", type=str, default=None, help="Optional registry name for this index.")
    install_parser.add_argument("--no-gitignore", action="store_true", help="Include files normally ignored by .gitignore.")
    install_parser.add_argument("--skip-index", action="store_true", help="Skip indexing; only configure MCP clients.")
    install_parser.set_defaults(handler=_run_setup)

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help="Remove cosk MCP server entry from all detected AI client configs",
        description=(
            "Scan for known AI client config files (Claude Desktop, VS Code, Cursor, Windsurf, Zed)\n"
            "and remove the 'cosk' MCP server entry from each one found."
        ),
    )
    uninstall_parser.set_defaults(handler=_run_uninstall)

    return parser


def _apply_no_gitignore(config: CoskConfig, args: argparse.Namespace) -> CoskConfig:
    if args.no_gitignore:
        return replace(config, extraction=replace(config.extraction, respect_gitignore=False))
    return config


def _make_manager(args: argparse.Namespace, config) -> IndexManager:
    return IndexManager(
        embedding_provider=server.load_embedding_provider(),
        config=config,
        default_db_dir=args.db_dir or server.DEFAULT_DB_DIR,
    )


def _run_index(args: argparse.Namespace) -> int:
    config = _apply_no_gitignore(get_cosk_config(), args)
    manager = _make_manager(args, config)
    human_mode = _is_interactive_terminal() and not args.json
    observer = RichIndexProgressObserver() if human_mode else None
    result = manager.sync(
        IndexBuildRequest(
            name=args.name,
            target_dir=args.target_dir,
            db_dir=args.db_dir,
            incremental=args.incremental,
            config=config,
        ),
        progress_observer=observer,
    )
    if human_mode:
        write_info("Next step: run `cosk serve` to start the MCP server.")
    else:
        write_json(asdict(result))
    return 0


def _run_search(args: argparse.Namespace) -> int:
    query = (args.query_flag or args.query or "").strip()
    if not query:
        raise ValueError("query is required")
    manager = _make_manager(args, get_cosk_config())
    try:
        top_k_applied, warnings = resolve_top_k(args.top_k, manager.config)
    except TopKValidationError as exc:
        raise ValueError(str(exc)) from exc
    context = manager.get_context(index_name=args.name, db_dir=args.db_dir)
    results = context.vector_store.search(query, top_k=top_k_applied)
    enriched, token_warnings = server.enrich_search_results(results)
    write_json(
        {
            "results": enriched,
            "top_k_requested": args.top_k,
            "top_k_applied": top_k_applied,
            "warnings": [*warnings, *token_warnings],
        }
    )
    return 0


def _run_neighbors(args: argparse.Namespace) -> int:
    node_id = (args.node_id_flag or args.node_id or "").strip()
    if not node_id:
        raise ValueError("node_id is required")
    manager = _make_manager(args, get_cosk_config())
    context = manager.get_context(index_name=args.name, db_dir=args.db_dir)
    neighbor_map = context.graph.get_neighbors(node_id)
    enriched, warnings = server.enrich_neighbor_entries(context.vector_store, neighbor_map)
    write_json({"inbound": enriched["inbound"], "outbound": enriched["outbound"], "warnings": warnings})
    return 0


def _run_expand(args: argparse.Namespace) -> int:
    file_path = (args.file_path_flag or args.file_path or "").strip()
    start_line = args.start_line_flag if args.start_line_flag is not None else args.start_line
    end_line = args.end_line_flag if args.end_line_flag is not None else args.end_line
    if not file_path or start_line is None or end_line is None:
        raise ValueError("file_path, start_line, and end_line are required")
    manager = _make_manager(args, get_cosk_config())
    context = manager.get_context(index_name=args.name, db_dir=args.db_dir)
    content = server.read_file_range(file_path, start_line, end_line, context_target_dir=context.target_dir)
    write_json({"content": content})
    return 0


def _run_find_usage(args: argparse.Namespace) -> int:
    entity_name = (args.entity_name_flag or args.entity_name or "").strip()
    if not entity_name:
        raise ValueError("entity_name is required")
    manager = _make_manager(args, get_cosk_config())
    context = manager.get_context(index_name=args.name, db_dir=args.db_dir)
    write_json(context.graph.find_usages(entity_name))
    return 0


def _run_watch(args: argparse.Namespace) -> int:
    config = _apply_no_gitignore(get_cosk_config(), args)
    manager = _make_manager(args, config)
    return run_watch_loop(manager=manager, target_dir=args.target_dir, db_dir=args.db_dir, name=args.name)


def _run_serve(args: argparse.Namespace) -> int:
    if not args.http:
        forwarded_args: list[str] = []
        if args.db_dir is not None:
            forwarded_args.extend(["--db-dir", str(args.db_dir)])
        if args.index_name is not None:
            forwarded_args.extend(["--index-name", args.index_name])
        server.main(forwarded_args)
        return 0
    config = get_cosk_config()
    manager = _make_manager(args, config)
    run_http_server(manager, args.host or config.transport.http_host, args.port or config.transport.http_port)
    return 0


def _run_inspect(args: argparse.Namespace) -> int:
    forwarded_args: list[str] = []
    if args.db_dir is not None:
        forwarded_args.extend(["--db-dir", str(args.db_dir)])
    return inspect.run(forwarded_args)


def _run_registry_list(args: argparse.Namespace) -> int:  # noqa: ARG001
    registry = load_registry()
    write_json(
        {
            "version": registry.version,
            "default": registry.default,
            "indexes": {name: asdict(entry) for name, entry in registry.indexes.items()},
        }
    )
    return 0


def _run_registry_remove(args: argparse.Namespace) -> int:
    registry = remove_index(args.name)
    write_json({"default": registry.default, "indexes": sorted(registry.indexes)})
    return 0


def _run_registry_set_default(args: argparse.Namespace) -> int:
    registry = set_default_index(args.name)
    write_json({"default": registry.default})
    return 0


def _run_setup(args: argparse.Namespace) -> int:
    if not args.skip_index:
        if args.target_dir is None:
            raise ValueError("--target-dir is required unless --skip-index is set")
        config = _apply_no_gitignore(get_cosk_config(), args)
        manager = _make_manager(args, config)
        observer = RichIndexProgressObserver() if _is_interactive_terminal() else None
        manager.sync(
            IndexBuildRequest(
                name=args.name,
                target_dir=args.target_dir,
                db_dir=args.db_dir,
                incremental=False,
                config=config,
            ),
            progress_observer=observer,
        )

    if args.db_dir is not None:
        db_dir = str(args.db_dir.resolve())
    elif args.target_dir is not None:
        db_dir = str((args.target_dir / ".lancedb").resolve())
    else:
        db_dir = str(server.DEFAULT_DB_DIR.resolve())

    cosk_cwd = str(Path(__file__).resolve().parents[1])
    run_setup_wizard(
        python_exe=sys.executable,
        cosk_cwd=cosk_cwd,
        db_dir=db_dir,
    )
    return 0


def _run_uninstall(args: argparse.Namespace) -> int:  # noqa: ARG001
    run_uninstall_wizard()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        exit_code = int(args.handler(args))
    except Exception as exc:  # noqa: BLE001
        write_error(str(exc))
        raise SystemExit(1) from exc
    if exit_code != 0:
        raise SystemExit(exit_code)


def _is_interactive_terminal() -> bool:
    return bool(sys.stdout.isatty() and sys.stderr.isatty())


def _cli_version() -> str:
    try:
        return version("cosk")
    except PackageNotFoundError:
        return "unknown"


if __name__ == "__main__":
    main()

