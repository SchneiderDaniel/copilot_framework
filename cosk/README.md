# Cosk

Cosk is a local MCP server (stdio transport) for AI-assisted codebase navigation and inspection.

## Installation

Python 3.11+ is required.

```bash
cd cosk
python -m pip install -e .
```

## Configuration

- Default vector database directory: `cosk/.lancedb`
- Default config file: `cosk/config/cosk.settings.yaml`
- `.gitignore` filtering toggle: `extraction.respect_gitignore: true`
- Optional embedding provider override:

```bash
set COSK_EMBEDDING_PROVIDER_FACTORY=your_module:build_provider
```

The factory must return an object implementing `embed(text: str) -> list[float]`.

## Indexing a target directory

Build or rebuild an index from a source tree:

```bash
cosk index --target-dir C:\path\to\repo
```

Build into a custom index directory:

```bash
cosk index --target-dir C:\path\to\repo --db-dir C:\path\to\repo.lancedb
```

By default, indexing respects layered `.gitignore` rules (root + nested) and also applies `exclude_dirs`.
Use this only-run override if you want to include ignored files:

```bash
cosk index --target-dir C:\path\to\repo --no-gitignore
```

## Starting the MCP server

Supported startup forms:

```bash
cosk serve
cosk serve --db-dir C:\path\to\repo.lancedb
```

Transport is **stdio**. Clients launch Cosk as a subprocess per session (no persistent background server process documented).

## Client connection overview

Example Claude Desktop-style config:

```json
{
  "mcpServers": {
    "cosk": {
      "command": "python",
      "args": ["-m", "cosk.mcp.server", "--db-dir", "C:/path/to/repo.lancedb"],
      "cwd": "C:/Users/you/Coding/copilot_framework/cosk"
    }
  }
}
```

See full setup guide: [`docs/client_setup.md`](docs/client_setup.md)

Any stdio-capable MCP client can launch Cosk, including Claude Desktop and LangChain-based test harnesses.

## MCP Tool Reference

### `cosk_semantic_search`

- Purpose: semantic retrieval of indexed nodes.
- Input schema: `{ "query_string": "string (required, non-blank)" }`
- Output schema: JSON array of objects with keys:
  `node_id`, `file_path`, `start_line`, `end_line`, `raw_signature`, `summary`
- Example request:

```json
{ "query_string": "authenticate user" }
```

- Example response:

```json
[
  {
    "node_id": "abc123",
    "file_path": "auth.py",
    "start_line": 10,
    "end_line": 22,
    "raw_signature": "def authenticate_user(...):",
    "summary": "Authenticate against local credentials."
  }
]
```

- Error behavior:
  - blank query -> MCP `INVALID_PARAMS`
  - runtime failure -> MCP `INTERNAL_ERROR`
  - empty index -> `[]`
  - server uses `top_k=5`

### `cosk_get_neighbors`

- Purpose: return inbound/outbound graph neighbors for a node.
- Input schema: `{ "node_id": "string (required, non-blank)" }`
- Output schema (success): JSON object:
  `{ "inbound": [{"node_id":"...","label":"imports|calls"}], "outbound": [...] }`
- Example request:

```json
{ "node_id": "pkg/module.py:42" }
```

- Example response:

```json
{
  "inbound": [{ "node_id": "pkg/caller.py:10", "label": "calls" }],
  "outbound": [{ "node_id": "pkg/callee.py:1", "label": "calls" }]
}
```

- Error behavior:
  - blank node_id -> MCP `INVALID_PARAMS`
  - missing graph -> MCP `INTERNAL_ERROR`
  - cycle/depth guardrails -> plain text notice (not MCP error), e.g.:
    - `Notice: You have already traversed this node. Please analyze your current context or use cosk_expand_definition.`
    - `Notice: Depth limit reached. Summarize your findings or expand a definition.`

### `cosk_expand_definition`

- Purpose: return raw source lines for a file range.
- Input schema:
  `{ "file_path": "string (required, non-blank)", "start_line": "int >=1", "end_line": "int >= start_line" }`
- Output schema (success): plain text (inclusive source slice).
- Example request:

```json
{ "file_path": "pkg/module.py", "start_line": 20, "end_line": 30 }
```

- Example response:

```text
def helper():
    return 42
```

- Error behavior:
  - blank `file_path` -> MCP `INVALID_PARAMS`
  - `start_line < 1` -> MCP `INVALID_PARAMS`
  - `end_line < start_line` -> MCP `INVALID_PARAMS`
  - unreadable file -> plain text: `Unable to read ...`
  - out-of-range request -> plain text: `Requested line range ...`

### `cosk_find_usage`

- Purpose: find usage contexts for an entity name from the relationship graph.
- Input schema: `{ "entity_name": "string (required, non-blank)" }`
- Output schema: JSON array of objects:
  `{ "file_path": "str", "line": "int", "context_node_id": "str" }`
- Example request:

```json
{ "entity_name": "authenticate_user" }
```

- Example response:

```json
[
  {
    "file_path": "routes.py",
    "line": 50,
    "context_node_id": "routes.py:50"
  }
]
```

- Error behavior:
  - blank entity_name -> MCP `INVALID_PARAMS`
  - missing graph -> MCP `INTERNAL_ERROR`

## Safety & Guardrails

Cosk tracks traversal context in `cosk/safety/middleware.py`:

- `record_search_origin` stores initial search origins.
- `safety_wrap_get_neighbors` applies revisit and depth checks.
- `record_expand_definition` unlocks deeper traversal after source expansion.

Guardrail notices are plain text responses, for example:

```text
Notice: You have already traversed this node. Please analyze your current context or use cosk_expand_definition.
Notice: Depth limit reached. Summarize your findings or expand a definition.
```

Cycle rejection occurs in graph building (`cosk/graph/builder.py`), and depth-limit guarded traversal applies during `cosk_get_neighbors`.

## Inspecting Cosk locally

Inspect index + graph status from terminal:

```bash
cosk inspect
cosk inspect --db-dir C:\path\to\repo.lancedb
```

Inspector shows:

- index validity and db path
- indexed nodes table
- graph stats (from loaded graph or rebuilt snapshot)
- vector DB metadata (table, columns, vector dimension, samples)

Example output:

```text
Header: db_path=... index_valid=True graph_source=rebuilt
Indexed Nodes Table ...
Graph Stats Table ...
Vector DB Panel ...
Footer: Tip: Use --db-dir to inspect a non-default index
```

## Troubleshooting

- **Invalid index path**: verify `--db-dir` points to a valid LanceDB with `skeleton_nodes`.
- **Graph unavailable**: graph-backed tools (`cosk_get_neighbors`, `cosk_find_usage`) return MCP `INTERNAL_ERROR` if graph is not loaded.
- **Embedding provider override fails**: ensure `COSK_EMBEDDING_PROVIDER_FACTORY=module:callable` is importable and returns an object with `embed`.
- **Client launch expectations**: MCP clients must spawn `python -m cosk.mcp.server` and communicate over stdio.

## Backward compatibility

The new CLI is primary (`cosk index`, `cosk serve`, `cosk inspect`), but module entrypoints remain supported:

```bash
python -m cosk.mcp.server
python -m cosk.mcp.server --target-dir C:\path\to\repo
python -m cosk.inspect
```
