"""Cosk setup wizard — detects AI client configs and injects the cosk MCP server entry."""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from cosk.cli.output import write_info


class _ConfigFormat(str, Enum):
    CLAUDE = "claude"   # { "mcpServers": { "cosk": { "command": ..., "args": [...], "cwd": ... } } }
    VSCODE = "vscode"   # { "servers": { "cosk": { "type": "stdio", "command": ..., "args": [...] } } }
    ZED = "zed"         # { "context_servers": { "cosk": { "command": { "path": ..., "args": [...] } } } }


@dataclass
class _KnownClient:
    name: str
    config_paths: list[Path]
    config_format: _ConfigFormat
    restart_hint: str


@dataclass
class DetectedClient:
    client: _KnownClient
    config_path: Path


def _home() -> Path:
    return Path.home()


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming")))


def _userprofile() -> Path:
    return Path(os.environ.get("USERPROFILE", str(_home())))


def _xdg_config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(_home() / ".config")))


def _known_clients() -> list[_KnownClient]:
    home = _home()
    appdata = _appdata()
    xdg = _xdg_config()
    return [
        _KnownClient(
            name="Claude Desktop",
            config_paths=[
                appdata / "Claude" / "claude_desktop_config.json",
                home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
                xdg / "claude" / "claude_desktop_config.json",
            ],
            config_format=_ConfigFormat.CLAUDE,
            restart_hint="Restart Claude Desktop to apply changes.",
        ),
        _KnownClient(
            name="VS Code (Copilot)",
            config_paths=[
                appdata / "Code" / "User" / "mcp.json",
                home / "Library" / "Application Support" / "Code" / "User" / "mcp.json",
                xdg / "Code" / "User" / "mcp.json",
            ],
            config_format=_ConfigFormat.VSCODE,
            restart_hint="Reload VS Code window (Ctrl+Shift+P → Reload Window).",
        ),
        _KnownClient(
            name="Cursor",
            config_paths=[
                _userprofile() / ".cursor" / "mcp.json",
                home / ".cursor" / "mcp.json",
            ],
            config_format=_ConfigFormat.CLAUDE,
            restart_hint="Restart Cursor to apply changes.",
        ),
        _KnownClient(
            name="Windsurf",
            config_paths=[
                home / ".codeium" / "windsurf" / "mcp_config.json",
                appdata / "Windsurf" / "mcp_config.json",
            ],
            config_format=_ConfigFormat.CLAUDE,
            restart_hint="Restart Windsurf to apply changes.",
        ),
        _KnownClient(
            name="Zed",
            config_paths=[
                xdg / "zed" / "settings.json",
                home / ".config" / "zed" / "settings.json",
            ],
            config_format=_ConfigFormat.ZED,
            restart_hint="Reload Zed settings (Ctrl+, → Reload).",
        ),
    ]


def detect_clients() -> list[DetectedClient]:
    """Return all AI clients whose config file exists on disk."""
    found: list[DetectedClient] = []
    for client in _known_clients():
        for path in client.config_paths:
            if path.exists():
                found.append(DetectedClient(client=client, config_path=path))
                break
    return found


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    return json.loads(raw) if raw else {}


def _patch_claude(data: dict, python_exe: str, cosk_cwd: str, db_dir: str) -> dict:
    data.setdefault("mcpServers", {})
    data["mcpServers"]["cosk"] = {
        "command": python_exe,
        "args": ["-m", "cosk.mcp.server", "--db-dir", db_dir],
        "cwd": cosk_cwd,
    }
    return data


def _patch_vscode(data: dict, python_exe: str, db_dir: str) -> dict:
    data.setdefault("servers", {})
    data["servers"]["cosk"] = {
        "type": "stdio",
        "command": python_exe,
        "args": ["-m", "cosk.mcp.server", "--db-dir", db_dir],
    }
    return data


def _patch_zed(data: dict, python_exe: str, db_dir: str) -> dict:
    data.setdefault("context_servers", {})
    data["context_servers"]["cosk"] = {
        "command": {
            "path": python_exe,
            "args": ["-m", "cosk.mcp.server", "--db-dir", db_dir],
        }
    }
    return data


def patch_client_config(
    config_path: Path,
    config_format: _ConfigFormat,
    python_exe: str,
    cosk_cwd: str,
    db_dir: str,
) -> tuple[bool, str]:
    """Patch a client config file with the cosk MCP server entry. Returns (ok, error)."""
    try:
        data = _load_json(config_path)
        if config_format == _ConfigFormat.CLAUDE:
            data = _patch_claude(data, python_exe, cosk_cwd, db_dir)
        elif config_format == _ConfigFormat.VSCODE:
            data = _patch_vscode(data, python_exe, db_dir)
        elif config_format == _ConfigFormat.ZED:
            data = _patch_zed(data, python_exe, db_dir)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _sep(label: str = "") -> None:
    if label:
        write_info(f"── {label} {'─' * max(0, 56 - len(label))}")
    else:
        write_info("─" * 60)


def agent_instruction_snippet(db_dir: str) -> str:
    """Markdown snippet for CLAUDE.md / agents.md / copilot instructions."""
    return (
        "## Cosk — Codebase Context (MCP)\n\n"
        "Cosk is an MCP server that provides semantic search and dependency graph\n"
        "navigation over the indexed codebase.\n\n"
        "### When to use\n"
        "- **Finding relevant code**: prefer `cosk_semantic_search` for concept-level queries.\n"
        "- **Understanding dependencies**: use `cosk_get_neighbors` (inbound/outbound).\n"
        "- **Reading a definition**: use `cosk_expand_definition` for raw source lines.\n"
        "- **Tracing a symbol**: use `cosk_find_usage` to find all call/import sites.\n\n"
        "### Available tools\n\n"
        "| Tool | Input | Purpose |\n"
        "|------|-------|---------|\n"
        "| `cosk_semantic_search` | `query_string` | Vector search across all definitions |\n"
        "| `cosk_get_neighbors` | `node_id` (`file:line`) | Graph neighbors of a node |\n"
        "| `cosk_expand_definition` | `node_id` | Raw source lines for a node |\n"
        "| `cosk_find_usage` | `entity_name` | All call/import sites for a symbol |\n\n"
        f"Index location: `{db_dir}`\n"
    )


def _manual_guide(python_exe: str, cosk_cwd: str, db_dir: str) -> str:
    return (
        "No known AI client config was found automatically.\n\n"
        "Supported clients: Claude Desktop, VS Code (Copilot), Cursor, Windsurf, Zed.\n"
        "If you use a different client, add the cosk MCP server entry manually.\n\n"
        "── Claude Desktop / Cursor / Windsurf (claude_desktop_config.json or mcp.json) ──\n\n"
        '  "mcpServers": {\n'
        '    "cosk": {\n'
        f'      "command": "{python_exe}",\n'
        '      "args": ["-m", "cosk.mcp.server", "--db-dir", "' + db_dir + '"],\n'
        f'      "cwd": "{cosk_cwd}"\n'
        "    }\n"
        "  }\n\n"
        "── VS Code / Copilot (.vscode/mcp.json or user mcp.json) ──\n\n"
        '  "servers": {\n'
        '    "cosk": {\n'
        '      "type": "stdio",\n'
        f'      "command": "{python_exe}",\n'
        '      "args": ["-m", "cosk.mcp.server", "--db-dir", "' + db_dir + '"]\n'
        "    }\n"
        "  }\n\n"
        "── Zed (~/.config/zed/settings.json) ──\n\n"
        '  "context_servers": {\n'
        '    "cosk": {\n'
        '      "command": {\n'
        f'        "path": "{python_exe}",\n'
        '        "args": ["-m", "cosk.mcp.server", "--db-dir", "' + db_dir + '"]\n'
        "      }\n"
        "    }\n"
        "  }\n\n"
        "After editing, restart your AI client."
    )


def run_setup_wizard(python_exe: str, cosk_cwd: str, db_dir: str) -> None:
    """Detect AI clients, patch their configs, and print the agent instruction snippet."""
    detected = detect_clients()

    if not detected:
        write_info(_manual_guide(python_exe, cosk_cwd, db_dir))
    else:
        for dc in detected:
            ok, err = patch_client_config(
                config_path=dc.config_path,
                config_format=dc.client.config_format,
                python_exe=python_exe,
                cosk_cwd=cosk_cwd,
                db_dir=db_dir,
            )
            if ok:
                write_info(f"  ✓  {dc.client.name}")
                write_info(f"     {dc.config_path}")
                write_info(f"     {dc.client.restart_hint}")
            else:
                write_info(f"  ✗  {dc.client.name}  —  patch failed: {err}")
                write_info(f"     Add manually to: {dc.config_path}")
            write_info("")

    write_info("")
    _sep("AGENT INSTRUCTIONS")
    write_info("Paste into your CLAUDE.md / agents.md / copilot instructions:\n")
    write_info(agent_instruction_snippet(db_dir))
    _sep()


def _remove_cosk_entry(config_path: Path, config_format: _ConfigFormat) -> tuple[bool, str, bool]:
    """Remove the cosk entry from a client config. Returns (ok, error, was_present)."""
    try:
        data = _load_json(config_path)
        was_present = False
        if config_format == _ConfigFormat.CLAUDE:
            was_present = "cosk" in data.get("mcpServers", {})
            data.get("mcpServers", {}).pop("cosk", None)
        elif config_format == _ConfigFormat.VSCODE:
            was_present = "cosk" in data.get("servers", {})
            data.get("servers", {}).pop("cosk", None)
        elif config_format == _ConfigFormat.ZED:
            was_present = "cosk" in data.get("context_servers", {})
            data.get("context_servers", {}).pop("cosk", None)
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True, "", was_present
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), False


def run_uninstall_wizard() -> None:
    """Detect AI clients and remove the cosk MCP server entry from each."""
    detected = detect_clients()

    write_info("")
    _sep("UNINSTALL — REMOVING COSK FROM CLIENT CONFIGS")

    if not detected:
        write_info("  No known AI client config files found on this machine.")
        write_info("  Nothing to remove.")
        _sep()
        return

    for dc in detected:
        ok, err, was_present = _remove_cosk_entry(dc.config_path, dc.client.config_format)
        if not ok:
            write_info(f"  ✗  {dc.client.name}  —  failed: {err}")
        elif was_present:
            write_info(f"  ✓  {dc.client.name}  —  cosk entry removed")
            write_info(f"     {dc.config_path}")
            write_info(f"     {dc.client.restart_hint}")
        else:
            write_info(f"  –  {dc.client.name}  —  no cosk entry found (skipped)")
        write_info("")

    _sep()
