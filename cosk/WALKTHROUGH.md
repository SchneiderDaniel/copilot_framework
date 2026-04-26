# Cosk — Code Walkthrough

**Cosk** = **Co**debase **Sk**eleton. It scans source files, extracts function/class signatures, embeds them into a vector store, builds a relationship graph, and exposes everything over an MCP server so an AI agent can semantically search and navigate any codebase.

---

## Big Picture: Data Flow

```
Source files on disk
       │
       ▼
extraction/parser.py          ← tree-sitter (or stdlib ast) parses code
       │  produces
       ▼
list[SkeletonNode]             ← (file_path, start_line, end_line, signature, docstring)
       │
       ├──► graph/builder.py   ← NetworkX DiGraph of import/call relationships
       │         │
       │         ▼
       │    graph/state.py     ← thread-safe in-memory singleton (get/set/clear)
       │
       └──► indexing/vector_store.py  ← LanceDB table, Gemini embeddings
                   │
                   ▼
            mcp/server.py      ← MCP stdio server with 3 tools
```

---

## Module-by-Module Breakdown

### `config.py` + `config/cosk.settings.yaml`

**What it does:** Loads and validates the single config object that drives the whole system.

**Key types:**

| Dataclass | Purpose |
|---|---|
| `CoskConfig` | Root config; holds `ExtractionSettings` |
| `ExtractionSettings` | `source_directory`, `exclude_dirs`, `follow_symlinks`, `strict`, `summarizer`, `supported_languages` |
| `LanguageSettings` | Per-language: name, file extensions, tree-sitter grammar package + module, `.scm` query file |
| `SummarizerSettings` | Optional `callable_path` (`module:attr`) for docstring generation |

**Key functions:**

- `get_cosk_config()` — reads `cosk.settings.yaml`, parses into `CoskConfig`, **cached** with `@lru_cache`. Call this everywhere instead of re-parsing.
- `validate_cosk_config(config)` — checks grammar packages are importable and summarizer callable is loadable. Optional startup check.

**`cosk.settings.yaml`:** Configures 23 languages (Python, JS, TS, Java, Go, Rust, C, C++, Ruby, Bash, JSON, YAML, TOML, CSS, HTML, Kotlin, Lua, Markdown, PHP, Scala, SQL, Swift, C#). Each entry maps file extension(s) → tree-sitter grammar package + an `.scm` query file.

`enabled` is auto-set to `false` if the grammar package isn't installed (uses `importlib.util.find_spec`).

---

### `extraction/`

#### `models.py` — The Core Data Type

```python
@dataclass(frozen=True, slots=True)
class SkeletonNode:
    file_path: str      # absolute path
    start_line: int     # 1-based
    end_line: int       # 1-based
    raw_signature: str  # e.g. "def my_func(x: int) -> str:"
    docstring: str      # extracted docstring, or "" if none
```

Every other module works with `list[SkeletonNode]`. This is the universal currency.

#### `registry.py` — Extension → Language Mapping

`build_extension_registry(config)` → `dict[str, LanguageSettings]`

Maps `.py` → Python settings, `.ts` → TypeScript settings, etc. Raises `ValueError` on duplicate extension across languages.

#### `query_loader.py` — Load `.scm` Tree-sitter Queries

`load_query_text(query_file, strict)` loads from the `extraction/queries/` package resource directory.
- `strict=True` → raises `FileNotFoundError` if missing
- `strict=False` → emits `RuntimeWarning` and returns `None` (file is skipped)

#### `queries/*.scm` — Tree-sitter Query Files (23 files)

One `.scm` file per language. Each query captures three named groups:
- `@definition` — the full AST node (function/class/method)
- `@signature` — the signature line(s) only
- `@docstring` — the docstring node if present

Example for Python (`python.scm`):
```scheme
(function_definition) @definition
```

#### `summarizers.py` — Optional Docstring Generator

`load_summarizer(callable_path)` dynamically imports a callable by `"module:attribute"` path.

If `callable_path` is `None`, returns `noop_summarizer` (returns `""`).

A real summarizer would be e.g. `"mypackage.ai:generate_summary"` — called as `summarizer(signature, file_path=..., language=..., **kwargs)`.

#### `parser.py` — The Extraction Engine

**Two entry points:**

1. `extract_skeleton_nodes(directory, *, summarize, config)` — walks a whole directory tree
2. `extract_file_skeleton_nodes(file_path, *, summarize, config)` — processes one file

**Per-file flow:**

```
1. Look up file extension in registry → get LanguageSettings
2. Load .scm query text
3. Try to build tree-sitter Parser for the language
   ├── Success → parse source → run query → collect @definition captures
   └── Fail (grammar not installed):
       ├── Python? → fallback to stdlib `ast` module
       └── Other?  → warn and skip (or raise if strict=True)
4. For each @definition:
   - Find matching @signature node (must be within definition byte range)
   - Find matching @docstring node (same rule)
   - If summarize=True and no docstring → call summarizer
   - Append SkeletonNode
```

**Python AST fallback** (`_extract_python_nodes_with_ast`): Uses `ast.walk` to find `FunctionDef`, `AsyncFunctionDef`, `ClassDef`. Extracts first-statement string literals as docstrings.

**`skeleton_nodes_to_json(nodes)`** — serializes to `list[dict]` via `dataclasses.asdict`.

---

### `graph/`

#### `exceptions.py`

```python
EdgeLabel = Literal["imports", "calls"]   # the two relationship types

@dataclass(frozen=True, slots=True)
class CycleEdge:
    source_node_id: str
    target_node_id: str
    labels: tuple[EdgeLabel, ...]

class CycleError(Exception):
    cycle_edges: list[CycleEdge]
```

#### `state.py` — Thread-safe Graph Singleton

Holds one `RelationshipGraph | None` in a module-level `_GRAPH` variable, protected by a `threading.Lock`.

- `get_graph()` — returns current graph or `None`
- `set_graph(graph)` — replaces current graph
- `clear_graph()` — sets to `None`

Used by the MCP server to access the graph across requests.

#### `builder.py` — Relationship Graph Construction

**Node ID:** `f"{file_path}:{start_line}"` — unique per definition.

**`build_graph(nodes)`** flow:

```
1. Add every SkeletonNode as a graph node (by node_id)
2. Build name→node_id index (from signatures, via AST parse)
3. For each node, parse its signature for:
   - import names  (ast.Import / ast.ImportFrom)
   - call names    (ast.Call)
4. For each found name, look up matching node_id in index
5. Add directed edge: source → target, labeled "imports" or "calls"
6. detect_cycles() — raise CycleError if any cycle found
```

**`RelationshipGraph`** wraps `nx.DiGraph` and exposes:
- `get_neighbors(node_id)` → `{"inbound": [...], "outbound": [...]}` with labels
- `detect_cycles()` → raises `CycleError` or does nothing

**`rebuild(nodes)`** — calls `build_graph`, then stores result in `graph.state`.

---

### `indexing/`

#### `embedding.py` — Embedding Providers

**`EmbeddingProvider` Protocol:**
```python
def embed(self, text: str) -> list[float]: ...
```

**`GeminiEmbeddingProvider`:**
- Default model: `"gemini-embedding-001"`
- API key resolution order: `GEMINI_API_KEY` env var → `GEMINI_KEY_PATH` env var → `.geminikey` file
- Exponential backoff retries: `base_delay=1s`, doubles each attempt, capped at `max_delay=8s`, default 3 attempts

**`build_node_embedding_text(node)`** → `signature + "\n" + docstring`

This is the text that gets embedded. Signature first ensures the function name/types dominate similarity.

#### `vector_store.py` — LanceDB Vector Store

**`SkeletonNodeVectorStore`** stores nodes in a LanceDB table with schema:

| Column | Type | Notes |
|---|---|---|
| `node_id` | string | SHA-256 of `file_path:start_line` |
| `file_path` | string | |
| `start_line` | int64 | |
| `end_line` | int64 | |
| `raw_signature` | string | |
| `summary` | string | = docstring |
| `vector` | list[float32, dim] | embedding |

**Key methods:**

- `rebuild_index(nodes)` — full rebuild using staging table pattern (atomic swap: write staging → drop old → create new → drop staging). Validates schema after.
- `upsert_nodes(nodes)` — incremental. Uses LanceDB `merge_insert("node_id")` for upsert semantics.
- `search(query, top_k=5)` — embeds query, runs ANN vector search, returns `list[SkeletonNodeSearchResult]`.
- `validate_index()` — checks `.lancedb` dir exists and all required columns present.

Default DB dir: `cosk/.lancedb` (inside package root).

---

### `mcp/server.py` — The MCP Server

**What it exposes:** An MCP stdio server named `"cosk"` with 3 tools.

| Tool | Input | What it does |
|---|---|---|
| `cosk_semantic_search` | `query_string` | Vector search, returns top-5 JSON results |
| `cosk_get_neighbors` | `node_id` | Returns graph inbound/outbound edges as JSON |
| `cosk_expand_definition` | `file_path, start_line, end_line` | Reads and returns those source lines verbatim |

**Startup sequence (`main()`):**

```
1. Parse CLI args (--target-dir, --db-dir)
2. Load embedding provider (env var COSK_EMBEDDING_PROVIDER_FACTORY or default Gemini)
3a. If --target-dir given:  extract nodes → rebuild_index
3b. If no --target-dir:     validate existing index (fail fast if missing)
4. create_mcp_server(vector_store).run("stdio")
```

**MCP SDK import conflict fix (`_load_mcp_sdk_modules`):**
Cosk has its own `mcp/` subdirectory which shadows the `mcp` PyPI package. The function temporarily removes the cosk package root from `sys.path` (and evicts `mcp.*` from `sys.modules`) before importing the real `mcp` SDK, then restores the path.

**Embedding provider injection:**
Set `COSK_EMBEDDING_PROVIDER_FACTORY=mymodule:make_provider` to plug in a custom embedding provider at startup (useful for testing without Gemini).

---

### `safety/`

Currently a stub — only `"""Safety guardrails package."""` in `__init__.py`. Planned for traversal depth limits and cycle detection guardrails.

---

## Key Design Decisions

| Decision | Reasoning |
|---|---|
| `SkeletonNode` is frozen + slots | Immutable, memory-efficient, hashable |
| LRU cache on `get_cosk_config()` | Config parsed once per process |
| Staging table in `rebuild_index` | Atomic swap prevents corrupt partial state |
| SHA-256 node_id in vector store | Stable cross-session identifier; decoupled from graph's `path:line` id |
| Python AST fallback in parser | Guarantees Python extraction even without tree-sitter grammar |
| MCP SDK path surgery | Avoids naming collision between cosk's `mcp/` package and PyPI `mcp` |
| `EdgeLabel` is `Literal` | Type-safe; only `"imports"` and `"calls"` are valid |

---

## How to Run

```bash
# Install in editable mode
python -m pip install -e .

# Start MCP server — extract fresh from a directory
python -m cosk.mcp.server --target-dir /path/to/project

# Start MCP server — load existing index
python -m cosk.mcp.server --db-dir /path/to/.lancedb

# Run tests
pytest tests/
```

**Required env for embeddings:**
```bash
export GEMINI_API_KEY=your_key_here
# or place key in .geminikey file at working directory
```

---

## File Map

```
cosk/
├── config.py                    # Config dataclasses + loader + validator
├── config/
│   └── cosk.settings.yaml       # Language definitions, extraction settings
├── extraction/
│   ├── models.py                # SkeletonNode dataclass
│   ├── registry.py              # Extension → LanguageSettings map
│   ├── query_loader.py          # Loads .scm files from package resources
│   ├── summarizers.py           # Dynamic summarizer loader
│   ├── parser.py                # Main extraction engine (tree-sitter + ast fallback)
│   └── queries/                 # 23 x .scm tree-sitter query files
├── graph/
│   ├── exceptions.py            # EdgeLabel, CycleEdge, CycleError
│   ├── state.py                 # Thread-safe graph singleton
│   └── builder.py               # build_graph(), RelationshipGraph
├── indexing/
│   ├── embedding.py             # EmbeddingProvider protocol, GeminiEmbeddingProvider
│   └── vector_store.py          # SkeletonNodeVectorStore (LanceDB)
├── mcp/
│   └── server.py                # FastMCP server, 3 tools, CLI entry point
├── safety/
│   └── __init__.py              # Stub — guardrails TBD
└── tests/                       # 17 test files
```
