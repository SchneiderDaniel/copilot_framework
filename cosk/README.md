# Cosk

Cosk helps AI agents understand your codebase by indexing structure, relationships, and source context for fast retrieval.

---

## Quick Start

### 1. Install cosk

Python 3.11+ is required.

```bash
python -m venv .venv
```

Activate:

- Windows (PowerShell): `.venv\Scripts\activate`
- macOS/Linux: `source .venv/bin/activate`

```bash
cd cosk
pip install -e .
```

### 2. Set up in one command

Run `cosk install` from inside the repo you want to index (use `..` to target the parent folder):

```bash
cd C:\path\to\your-repo\cosk
cosk install --target-dir ..
```

Or point it at any directory:

```bash
cosk install --target-dir C:\path\to\your-repo
```

That's it. Cosk will:

1. **Index** the repository (scans files, builds embeddings and graph).
2. **Auto-configure** any detected AI clients (Claude Desktop, VS Code Copilot, Cursor, Windsurf, Zed).
3. **Print a snippet** to paste into your `CLAUDE.md` / `agents.md` / copilot instructions.

### 3. Use it

Your AI client now has access to the `cosk_semantic_search`, `cosk_get_neighbors`, `cosk_expand_definition`, and `cosk_find_usage` MCP tools automatically.

### Uninstall

Remove cosk from all detected AI client configs:

```bash
cosk uninstall
```

---

## Command Reference

| Command | Description |
| --- | --- |
| `cosk install --target-dir <repo>` | **One-shot onboarding** — index + configure all AI clients. |
| `cosk install --target-dir <repo> --skip-index` | Configure clients only (skip re-indexing). |
| `cosk uninstall` | Remove cosk MCP entry from all detected AI client configs. |
| `cosk index --target-dir <repo>` | Build or rebuild the index manually. |
| `cosk serve --db-dir <repo>/.lancedb` | Start the MCP stdio server. |
| `cosk search --query "<text>" --db-dir <repo>/.lancedb` | Run a semantic search from the CLI. |
| `cosk neighbors --node-id "<file>:<line>" --db-dir <repo>/.lancedb` | Inspect graph relationships for a node. |
| `cosk expand --file-path <file> --start-line <n> --end-line <m>` | Print raw source lines for a range. |
| `cosk find-usage --entity-name "<symbol>" --db-dir <repo>/.lancedb` | Find usage contexts for a symbol. |
| `cosk watch --target-dir <repo>` | Watch files and reindex incrementally on change. |
| `cosk inspect --db-dir <repo>/.lancedb` | Print local index diagnostics. |
| `cosk registry list` | List named indexes in the local registry. |
| `cosk registry remove --name <name>` | Remove a named index from the registry. |
| `cosk registry set-default --name <name>` | Set the default named index. |

---

## Detailed Setup

### Virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

cd cosk
python -m pip install -e .
# optional token counting support
python -m pip install -e ".[tokens]"
```

### Verify installation

```bash
cosk --version
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

## Indexing options

Build or rebuild an index:

```bash
cosk index --target-dir C:\path\to\repo
```

Build into a custom index directory:

```bash
cosk index --target-dir C:\path\to\repo --db-dir C:\path\to\repo.lancedb
```

Include files normally filtered by `.gitignore`:

```bash
cosk index --target-dir C:\path\to\repo --no-gitignore
```

## Starting the MCP server manually

```bash
cosk serve
cosk serve --db-dir C:\path\to\repo.lancedb
```

Transport is **stdio**. Clients launch Cosk as a subprocess per session.

## Keeping the index current

When an AI agent (or you) modifies files, the index goes stale. The recommended approach is **two terminals**:

**Terminal 1 — file watcher (keep running):**

```bash
cosk watch --target-dir C:\path\to\repo
```

This watches the filesystem and reindexes changed files incrementally in real time. The MCP server reads from the same LanceDB directory and picks up updates automatically between queries — no restart needed.

**Terminal 2 — normal work** (AI client connects to `cosk serve` as usual via MCP config).

**Alternative — manual rebuild** (simpler, slower):

```bash
# Run once before or after an agent session
cosk index --target-dir C:\path\to\repo
```

## Manual client configuration

If your client was not auto-configured by `cosk install`, add an entry manually.

> ⚠️ **GitHub Copilot CLI users:** The config file must be placed at **`~/.copilot/mcp-config.json`**.
> A project-level `.copilot/mcp-config.json` is not read by the CLI and the tools will not appear.
> See [`docs/client_setup.md`](docs/client_setup.md) for the full Copilot CLI setup guide.

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

See full per-client guide: [`docs/client_setup.md`](docs/client_setup.md)

---

## When to use cosk vs grep

Choose based on the nature of your question:

| Question type | Right tool | Example |
|---|---|---|
| "How does X work?" | `cosk_semantic_search` | *"How does cosk handle retries when the Gemini API fails?"* |
| "Where is concept Y implemented?" | `cosk_semantic_search` | *"Where is the dependency graph built during indexing?"* |
| "What depends on / calls Z?" | `cosk_get_neighbors` | *"What does `GeminiEmbeddingProvider` depend on?"* |
| "Where is symbol Z used?" | `cosk_find_usage` | *"Where is `SkeletonNode` referenced across the codebase?"* |
| "Show me the full body of function Z" | `cosk_expand_definition` | *"What exactly does `GeminiEmbeddingProvider.embed` do?"* |
| "Find all symbols whose name contains string X" | **grep** | *"Find all functions with the word 'embed' in their name"* |
| "Which files contain literal string X?" | **grep** | *"Which files contain the string 'lancedb'"* |

The clearest signal for cosk is when the question is about **how**, **why**, or **what depends on what**. The clearest signal for grep is when you are matching a literal name or string pattern.

---

## MCP Tool Reference

### `cosk_semantic_search`

- Purpose: semantic retrieval of indexed nodes.
- Input: `{ "query_string": "string (required, non-blank)" }`
- Output: JSON array — `node_id`, `file_path`, `start_line`, `end_line`, `raw_signature`, `summary`
- **When NOT to use**: do not use this for exact name/substring lookups (e.g. "find all functions containing the word X"). It is a vector similarity search, not a name filter — use **grep** for pattern matching instead.

```json
{ "query_string": "authenticate user" }
```

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

Errors: blank query → `INVALID_PARAMS`; runtime failure → `INTERNAL_ERROR`; empty index → `[]`.

### `cosk_get_neighbors`

- Purpose: inbound/outbound graph neighbors for a node.
- Input: `{ "node_id": "string (required, non-blank)" }`
- Output: `{ "inbound": [{"node_id":"...","label":"imports|calls"}], "outbound": [...] }`

Errors: blank node_id → `INVALID_PARAMS`; missing graph → `INTERNAL_ERROR`. Cycle/depth notices are plain text responses, not MCP errors.

### `cosk_expand_definition`

- Purpose: raw source lines for a file range.
- Input: `{ "file_path": "string", "start_line": int, "end_line": int }`
- Output: plain text (inclusive source slice).

Errors: blank path or invalid range → `INVALID_PARAMS`; unreadable file → plain text notice.

### `cosk_find_usage`

- Purpose: find usage contexts for a symbol from the relationship graph.
- Input: `{ "entity_name": "string (required, non-blank)" }`
- Output: `[{ "file_path": "str", "line": int, "context_node_id": "str" }]`

Errors: blank entity_name → `INVALID_PARAMS`; missing graph → `INTERNAL_ERROR`.

---

## Safety & Guardrails

Cosk tracks traversal context (`cosk/safety/middleware.py`):

- `record_search_origin` — stores initial search origins.
- `safety_wrap_get_neighbors` — applies revisit and depth checks.
- `record_expand_definition` — unlocks deeper traversal after source expansion.

Guardrail notices are plain text, for example:

```text
Notice: You have already traversed this node. Please analyze your current context or use cosk_expand_definition.
Notice: Depth limit reached. Summarize your findings or expand a definition.
```

## Inspecting the index

```bash
cosk inspect
cosk inspect --db-dir C:\path\to\repo.lancedb
```

Shows index validity, indexed nodes, graph stats, and vector DB metadata.

## Troubleshooting

- **Invalid index path**: verify `--db-dir` points to a valid LanceDB directory with `skeleton_nodes`.
- **Graph unavailable**: `cosk_get_neighbors` and `cosk_find_usage` return `INTERNAL_ERROR` if the graph is not loaded.
- **Embedding provider override fails**: ensure `COSK_EMBEDDING_PROVIDER_FACTORY=module:callable` is importable and returns an object with `embed`.
- **Client not auto-detected**: use `cosk install --skip-index` after adding the client, or configure manually via [`docs/client_setup.md`](docs/client_setup.md).

## Backward compatibility

The new CLI is primary, but module entrypoints remain supported:

```bash
python -m cosk.mcp.server
python -m cosk.mcp.server --target-dir C:\path\to\repo
python -m cosk.inspect
```

