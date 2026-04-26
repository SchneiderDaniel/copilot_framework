from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from cosk.config import get_cosk_config
from cosk import inspect
from cosk.mcp import server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cosk CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser(
        "index",
        help="Build or rebuild the local index only.",
        description="Build or rebuild the local index only.",
    )
    index_parser.add_argument("--target-dir", type=Path, required=True, help="Directory to extract and index.")
    index_parser.add_argument(
        "--db-dir",
        type=Path,
        default=server.DEFAULT_DB_DIR,
        help="LanceDB directory path.",
    )
    index_parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Disable .gitignore-based exclusion for this index run.",
    )
    index_parser.set_defaults(handler=_run_index)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Load an existing index and run MCP over stdio.",
        description="Load an existing index and run MCP over stdio.",
    )
    serve_parser.add_argument("--db-dir", type=Path, default=None, help="LanceDB directory path.")
    serve_parser.set_defaults(handler=_run_serve)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Print local index and graph diagnostics.",
        description="Print local index and graph diagnostics.",
    )
    inspect_parser.add_argument("--db-dir", type=Path, default=None, help="LanceDB directory path.")
    inspect_parser.set_defaults(handler=_run_inspect)

    return parser


def _run_index(args: argparse.Namespace) -> int:
    base_config = get_cosk_config()
    config = base_config
    if args.no_gitignore:
        config = replace(
            base_config,
            extraction=replace(base_config.extraction, respect_gitignore=False),
        )
    provider = server.load_embedding_provider()
    server.build_index_from_target(args.target_dir, args.db_dir, provider, config=config)
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    forwarded_args: list[str] = []
    if args.db_dir is not None:
        forwarded_args.extend(["--db-dir", str(args.db_dir)])
    server.main(forwarded_args)
    return 0


def _run_inspect(args: argparse.Namespace) -> int:
    forwarded_args: list[str] = []
    if args.db_dir is not None:
        forwarded_args.extend(["--db-dir", str(args.db_dir)])
    return inspect.run(forwarded_args)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code = int(args.handler(args))
    if exit_code != 0:
        raise SystemExit(exit_code)
