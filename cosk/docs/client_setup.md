# Claude Desktop Client Setup for Cosk

## Prerequisites

- Cosk installed (`python -m pip install -e .` from `cosk/`)
- A valid Python executable path
- Either:
  - an existing index directory (`--db-dir`), or
  - a target directory to index (`--target-dir`)

## How Claude Desktop launches Cosk

Claude Desktop starts Cosk as a subprocess and communicates over stdio.  
There is no separate long-running background service configuration required.

## Step-by-step setup

1. Locate your Claude Desktop MCP config file.
2. Add/update the `mcpServers` object.
3. Add a `cosk` server entry with `command`, `args`, and optional `cwd`/`env`.
4. Save config and restart Claude Desktop.

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

## Verification

1. Restart Claude Desktop.
2. Confirm Cosk appears as connected MCP server.
3. Confirm tools are available:
   - `cosk_semantic_search`
   - `cosk_get_neighbors`
   - `cosk_expand_definition`
   - `cosk_find_usage`

## Troubleshooting

- **Bad Python path**: use absolute Python executable path in `command`.
- **Missing install**: run `python -m pip install -e .` from `cosk/`.
- **Invalid DB**: verify `--db-dir` points to a valid Cosk index.
- **Embedding credentials/provider**: configure `GEMINI_API_KEY` or `COSK_EMBEDDING_PROVIDER_FACTORY`.
- **Graph-backed tool failures**: `cosk_get_neighbors` / `cosk_find_usage` can return MCP `INTERNAL_ERROR` if graph state is unavailable.

## See also

- Main docs: [`../README.md`](../README.md)
