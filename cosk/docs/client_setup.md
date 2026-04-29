# MCP Client Setup for Cosk

## TL;DR — one command

```bash
cosk install --target-dir C:\path\to\repo
```

This indexes your repo **and** automatically patches the config for any detected AI client
(Claude Desktop, VS Code Copilot, Cursor, Windsurf, Zed). It also prints a ready-to-paste
snippet for `CLAUDE.md` / `agents.md` / copilot instructions.

To remove cosk from all detected client configs:

```bash
cosk uninstall
```

If your client is not auto-detected, follow the manual steps below.

---

## Prerequisites

- Cosk installed (`python -m pip install -e .` from `cosk/`)
- A valid Python executable path
- Either:
  - an existing index directory (`--db-dir`), or
  - a target directory to index (`--target-dir`)

## Generic MCP stdio setup

Any MCP client can launch Cosk as a subprocess over stdio.  
There is no separate long-running background service configuration required.

Use this generic server definition shape:

```json
{
  "mcpServers": {
    "cosk": {
      "command": "python",
      "args": ["-m", "cosk.mcp.server", "--db-dir", "C:/path/to/repo.lancedb"],
      "cwd": "C:/path/to/cosk"
    }
  }
}
```

## Step-by-step setup

1. Open your MCP client configuration file.
2. Add/update the `mcpServers` object.
3. Add a `cosk` server entry with `command`, `args`, and optional `cwd`/`env`.
4. Save config and restart your MCP client.

## Config examples

### Minimal

```json
{
  "mcpServers": {
    "cosk": {
      "command": "python",
      "args": ["-m", "cosk.mcp.server"],
      "cwd": "C:/Users/you/Coding/copilot_framework/cosk"
    }
  }
}
```

### With `--target-dir`

```json
{
  "mcpServers": {
    "cosk": {
      "command": "python",
      "args": ["-m", "cosk.mcp.server", "--target-dir", "C:/path/to/repo"],
      "cwd": "C:/Users/you/Coding/copilot_framework/cosk"
    }
  }
}
```

### With `--db-dir`

```json
{
  "mcpServers": {
    "cosk": {
      "command": "python",
      "args": ["-m", "cosk.mcp.server", "--db-dir", "C:/path/to/repo.lancedb"],
      "cwd": "C:/Users/you/Coding/copilot_framework/cosk",
      "env": {
        "COSK_EMBEDDING_PROVIDER_FACTORY": "your_module:build_provider"
      }
    }
  }
}
```

## GitHub Copilot CLI

> ⚠️ **`cosk install` does not auto-detect GitHub Copilot CLI.** Manual setup is required.

GitHub Copilot CLI reads MCP server config from **`~/.copilot/mcp-config.json`** (user-level).
A project-level `.copilot/mcp-config.json` file is **ignored** — the tools will not appear.

The config location can be changed by setting the `COPILOT_HOME` environment variable.

**Steps:**

1. Open (or create) `~/.copilot/mcp-config.json`.
2. Add the cosk entry:

```json
{
  "mcpServers": {
    "cosk": {
      "command": "C:/path/to/.venv/Scripts/python.exe",
      "args": [
        "-m", "cosk.mcp.server",
        "--db-dir", "C:/path/to/repo/.lancedb"
      ],
      "cwd": "C:/path/to/cosk"
    }
  }
}
```

3. **Fully restart** the Copilot CLI (start a new session — do not resume an old one).
4. Verify with `/env` in the CLI — cosk should appear under MCP servers.

---

## Verification

1. Restart your MCP client.
2. Confirm Cosk appears as connected MCP server.
3. Confirm tools are available:
   - `cosk_semantic_search`
   - `cosk_get_neighbors`
   - `cosk_get_symbol_source`
   - `cosk_find_usage`

## Troubleshooting

- **Bad Python path**: use absolute Python executable path in `command`.
- **Missing install**: run `python -m pip install -e .` from `cosk/`.
- **Invalid DB**: verify `--db-dir` points to a valid Cosk index.
- **Embedding credentials/provider**: configure `GEMINI_API_KEY` or `COSK_EMBEDDING_PROVIDER_FACTORY`.
- **Graph-backed tool failures**: `cosk_get_neighbors` / `cosk_find_usage` can return MCP `INTERNAL_ERROR` if graph state is unavailable.

## See also

- Main docs: [`../README.md`](../README.md)
