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


def _known_clients(target_dir: Path | None = None) -> list[_KnownClient]:
    home = _home()
    appdata = _appdata()
    xdg = _xdg_config()

    # Candidate paths for GitHub Copilot CLI project-level config (.copilot/mcp-config.json).
    # The file lives at the repo root, so we check target_dir first, then cwd and its parent
    # (user may run `cosk install` from a subdir like `cosk/`).
    copilot_cli_paths: list[Path] = []
    if target_dir is not None:
        copilot_cli_paths.append(target_dir / ".copilot" / "mcp-config.json")
    copilot_cli_paths.append(Path.cwd() / ".copilot" / "mcp-config.json")
    copilot_cli_paths.append(Path.cwd().parent / ".copilot" / "mcp-config.json")

    return [
        _KnownClient(
            name="GitHub Copilot CLI",
            config_paths=copilot_cli_paths,
            config_format=_ConfigFormat.CLAUDE,
            restart_hint="No restart needed — Copilot CLI picks up the new MCP server automatically.",
        ),
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


def detect_clients(target_dir: Path | None = None) -> list[DetectedClient]:
    """Return all AI clients whose config file exists on disk."""
    found: list[DetectedClient] = []
    for client in _known_clients(target_dir):
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
        "### Task → tool routing (mandatory)\n\n"
        "| Task | Tool |\n"
        "|------|------|\n"
        "| Symbol by name / substring / regex | `cosk_search_by_name` |\n"
        "| Concept / \"how does X work\" | `cosk_semantic_search` |\n"
        "| What calls or depends on X | `cosk_get_neighbors` |\n"
        "| Where is symbol X used | `cosk_find_usage` |\n"
        "| Show me the body of X | `cosk_get_symbol_source` |\n"
        "| Literal string in any file | `grep` |\n\n"
        "Never use grep for code exploration. grep is only allowed for searching literal strings in file content.\n\n"
        "### Available tools\n\n"
        "| Tool | Input | Purpose |\n"
        "|------|-------|---------|\n"
        "| `cosk_search_by_name` | `query`, optional `kind`, optional `index_name` | Exact / substring / regex symbol-name search |\n"
        "| `cosk_semantic_search` | `query_string` | Vector search across all definitions |\n"
        "| `cosk_get_neighbors` | `node_id` (`file:line`) | Graph neighbors of a node |\n"
        "| `cosk_get_symbol_source` | `node_ids`, optional `index_name` | Batched source retrieval for node IDs |\n"
        "| `cosk_find_usage` | `entity_name` | All call/import sites for a symbol |\n\n"
        f"Index location: `{db_dir}`\n"
    )


def _mcp_config_snippet(python_exe: str, cosk_cwd: str, db_dir: str) -> str:
    """One-stop MCP config reference shown after every install (detected or not)."""
    return (
        "Add one of these blocks to your AI client's MCP config file:\n\n"
        "  Claude Desktop · Cursor · Windsurf · GitHub Copilot CLI\n"
        "  (claude_desktop_config.json / mcp.json / .copilot/mcp-config.json)\n\n"
        '    "mcpServers": {\n'
        '      "cosk": {\n'
        f'        "command": "{python_exe}",\n'
        '        "args": ["-m", "cosk.mcp.server", "--db-dir", "' + db_dir + '"],\n'
        f'        "cwd": "{cosk_cwd}"\n'
        "      }\n"
        "    }\n\n"
        "  VS Code  (.vscode/mcp.json or user mcp.json)\n\n"
        '    "servers": {\n'
        '      "cosk": {\n'
        '        "type": "stdio",\n'
        f'        "command": "{python_exe}",\n'
        '        "args": ["-m", "cosk.mcp.server", "--db-dir", "' + db_dir + '"]\n'
        "      }\n"
        "    }\n\n"
        "  Zed  (~/.config/zed/settings.json)\n\n"
        '    "context_servers": {\n'
        '      "cosk": {\n'
        '        "command": {\n'
        f'          "path": "{python_exe}",\n'
        '          "args": ["-m", "cosk.mcp.server", "--db-dir", "' + db_dir + '"]\n'
        "        }\n"
        "      }\n"
        "    }\n"
    )


def run_setup_wizard(python_exe: str, cosk_cwd: str, db_dir: str, target_dir: str | None = None) -> None:
    """Detect AI clients, patch their configs, and print the agent instruction snippet."""
    target_dir_path = Path(target_dir) if target_dir else None
    detected = detect_clients(target_dir_path)

    if not detected:
        write_info("  No known AI client config files were found — nothing was patched automatically.")
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
    _sep("MCP CONFIG")
    write_info(_mcp_config_snippet(python_exe, cosk_cwd, db_dir))
    _sep()

    write_info("")
    _sep("AGENT INSTRUCTIONS")
    write_info("Paste into your CLAUDE.md / agents.md / copilot instructions:\n")
    write_info(agent_instruction_snippet(db_dir))
    _sep()

    _sep("NEXT STEPS")
    write_info("")
    write_info("  cosk serve is auto-started by your AI client — no manual step needed.")
    write_info("")
    watch_dir = target_dir or "<path-to-your-repo>"
    write_info("  To keep the index current while the agent modifies files,")
    write_info("  run this in a background terminal (keep it running):")
    write_info("")
    write_info(f"    cosk watch --target-dir {watch_dir}")
    write_info("")
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


def run_uninstall_wizard(target_dir: str | None = None) -> None:
    """Detect AI clients and remove the cosk MCP server entry from each."""
    target_dir_path = Path(target_dir) if target_dir else None
    detected = detect_clients(target_dir_path)

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
