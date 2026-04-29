# Cosk — Code Walkthrough

## What Is Cosk?

**Cosk** stands for **Co**debase **Sk**eleton. The core idea is this: instead of giving an AI agent raw source files (which are huge and expensive to process), you give it a *skeleton* — just the function and class signatures plus their docstrings, stripped of all implementation details.

From that skeleton, Cosk does two things:

1. **Embeds every definition** into a vector database so an AI can ask "find me code related to authentication" and get back the most semantically similar definitions.
2. **Builds a relationship graph** between definitions (who imports who, who calls who) so an AI can navigate dependencies: "what calls `parse_token`? what does `build_graph` depend on?"

Both of these are then served over the [MCP (Model Context Protocol)](https://modelcontextprotocol.io) — a standard stdio protocol that AI assistants like Claude use to call external tools.

The end result: an MCP server that lets an AI agent intelligently navigate your codebase without reading every line of every file.

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
       ├──► graph/builder.py   ← builds a NetworkX directed graph of relationships
       │         │                 (edges labeled "imports" or "calls")
       │         ▼
       │    graph/state.py     ← stores the graph as a thread-safe in-memory singleton
       │
       └──► indexing/vector_store.py  ← embeds each node with Gemini, stores in LanceDB
                   │
                   ▼
            mcp/server.py      ← stdio MCP server exposing 3 tools to AI agents
```

The `list[SkeletonNode]` is the shared intermediate format. Every module either produces it (extraction) or consumes it (graph, indexing). Nothing downstream touches raw source files.

---

## Module-by-Module Breakdown

---

### `config.py` + `config/cosk.settings.yaml`

#### What problem does this solve?

The parser needs to know: which file extensions exist, which tree-sitter grammar to use for each, where the query files live, which directories to skip, whether to raise errors or silently skip on failure, and whether to auto-generate docstrings.

All of this is driven by a single YAML file. `config.py` reads that YAML and turns it into typed Python dataclasses so the rest of the code can work with strong types, not raw dictionaries.

#### The config hierarchy

```
CoskConfig
└── ExtractionSettings
    ├── source_directory: str         # root dir to walk (default ".")
    ├── exclude_dirs: tuple[str, ...] # skip these directory names (e.g. ".git", "__pycache__")
    ├── follow_symlinks: bool         # whether to follow symlinks while walking
    ├── strict: bool                  # True = crash on any parse/query failure; False = warn and skip
    ├── summarizer: SummarizerSettings
    │   ├── callable_path: str|None   # "module:attr" path to a docstring-generator function
    │   └── kwargs: dict              # extra kwargs passed to that function
    └── supported_languages: tuple[LanguageSettings, ...]
        └── LanguageSettings (one per language):
            ├── name: str             # e.g. "python"
            ├── extensions: tuple     # e.g. (".py",)
            ├── grammar_package: str  # pip package name, e.g. "tree_sitter_python"
            ├── grammar_module: str   # attribute inside that package, e.g. "language"
            ├── query_file: str       # filename in extraction/queries/, e.g. "python.scm"
            └── enabled: bool         # auto-set False if grammar_package not installed
```

#### Key functions

**`get_cosk_config() -> CoskConfig`** — the main entry point. Reads `config/cosk.settings.yaml`, parses it into the dataclass hierarchy above, and **caches the result with `@lru_cache`**. This means the YAML file is only read and parsed once per process. All other modules call this function rather than loading config themselves.

**`validate_cosk_config(config)`** — an optional deep check. It actually tries to `import_module` each enabled grammar package and verifies the attribute exists. It also calls `load_summarizer` to verify that callable is importable. Use this at startup if you want to fail fast on misconfiguration rather than discovering broken grammars only when the first file of that language is parsed.

**`_parse_config(data)`** — the internal parser. The `enabled` logic here is important: it calls `importlib.util.find_spec(grammar_package)` to check whether the grammar is actually installed. If not, `enabled` becomes `False` even if the YAML says `enabled: true`. This lets the code run gracefully on environments where some language grammars weren't installed.

#### The settings file

`config/cosk.settings.yaml` defines 23 languages. Each entry looks like this:

```yaml
- name: python
  extensions: [.py]
  grammar_package: tree_sitter_python
  grammar_module: language
  query_file: python.scm
  enabled: true
```

Notably, some languages have multiple extensions (e.g. JavaScript covers `.js`, `.mjs`, `.cjs`) and some grammar modules have non-standard attribute names (TypeScript uses `language_typescript` instead of `language`).

---

### `extraction/`

The extraction package is responsible for turning source files into `SkeletonNode` objects. It has five components.

---

#### `models.py` — The Core Data Type

```python
@dataclass(frozen=True, slots=True)
class SkeletonNode:
    file_path: str      # absolute POSIX path to the source file
    start_line: int     # line where this definition starts (1-based)
    end_line: int       # line where this definition ends (1-based)
    raw_signature: str  # the signature text, e.g. "def my_func(x: int) -> str:"
    docstring: str      # the docstring if found, otherwise ""
```

This is the single most important type in the codebase. Everything downstream — the graph builder, the vector store, the MCP tools — works with lists of `SkeletonNode`. It is `frozen=True` (immutable, safe to hash and use in sets) and `slots=True` (more memory-efficient than `__dict__`-based objects).

**Example of what a SkeletonNode looks like for a Python function:**

Given this source file at `/project/auth.py`:
```python
def verify_token(token: str) -> bool:
    """Check if the JWT token is valid and not expired."""
    ...
```

The resulting `SkeletonNode` would be:
```python
SkeletonNode(
    file_path="/project/auth.py",
    start_line=1,
    end_line=3,
    raw_signature='def verify_token(token: str) -> bool:',
    docstring='"""Check if the JWT token is valid and not expired."""',
)
```

---

#### `registry.py` — Extension → Language Mapping

`build_extension_registry(config) -> dict[str, LanguageSettings]`

This function flattens the `supported_languages` list into a simple dictionary keyed by file extension. For example:

```python
{
    ".py":  LanguageSettings(name="python", ...),
    ".js":  LanguageSettings(name="javascript", ...),
    ".mjs": LanguageSettings(name="javascript", ...),  # same language, different extension
    ".ts":  LanguageSettings(name="typescript", ...),
    ...
}
```

When the parser encounters a file, it looks up `path.suffix` in this dictionary to find out which grammar and query file to use. Languages with `enabled=False` are excluded entirely.

It raises `ValueError` if two languages map to the same extension — this would be a YAML misconfiguration and is a hard error.

---

#### `query_loader.py` — Load `.scm` Tree-sitter Query Files

`load_query_text(query_file, strict) -> str | None`

Loads a tree-sitter query file from the `extraction/queries/` package resource directory. It uses `importlib.resources.files()` so this works correctly whether cosk is installed as a package or run from source.

The `strict` flag controls failure behavior:
- `strict=True` → `FileNotFoundError` (crash immediately — good for CI)
- `strict=False` → `RuntimeWarning` + returns `None` (the parser will skip this language gracefully)

---

#### `queries/*.scm` — Tree-sitter Query Files (23 files)

Tree-sitter queries are written in a Lisp-like pattern language (`.scm` = Scheme syntax). You describe the AST node shapes you want to match, and attach capture names (prefixed with `@`) to extract specific sub-nodes.

Every `.scm` file in cosk captures exactly three things:

| Capture name | What it captures |
|---|---|
| `@definition` | The entire function/class AST node (used to get line range) |
| `@signature` | The name identifier or header of the definition |
| `@docstring` | The first string literal in the body, if it's a docstring |

**The Python query (`python.scm`) in full:**

```scheme
[
  (function_definition)
  (class_definition)
] @definition

[
  (function_definition
    name: (identifier) @signature)
  (class_definition
    name: (identifier) @signature)
]

[
  (function_definition
    body: (block
      (expression_statement
        (string) @docstring)))
  (class_definition
    body: (block
      (expression_statement
        (string) @docstring)))
] @export
```

Reading this line by line:
- First block: capture every `function_definition` and `class_definition` node as `@definition`. This gives us the byte range of the whole function/class.
- Second block: capture the `name` identifier node inside each definition as `@signature`. This is just the function/class name, not the full signature — the parser code uses the byte range from `@definition` to find the full first line.
- Third block: capture the first `(string)` inside the body's block if it appears as a standalone expression (which is what a docstring is — a string literal that's just an expression, not assigned to anything).

Other languages have similar patterns adapted to their AST shape.

---

#### `summarizers.py` — Optional AI Docstring Generator

When a definition has no docstring, cosk can optionally call an external function to generate one (e.g. using an LLM). This module handles loading that function.

**`load_summarizer(callable_path) -> SummarizerCallable`**

`callable_path` is a string in `"module:attribute"` format, e.g. `"mypackage.ai:generate_summary"`. The function splits on `:`, imports the module, and returns `getattr(module, attribute)`.

If `callable_path` is `None` or empty, it returns `noop_summarizer` — a function that just returns `""`. This means summarization is fully opt-in and has zero overhead by default.

The summarizer signature that cosk expects:
```python
def my_summarizer(signature: str, *, file_path: str, language: str, **kwargs) -> str:
    ...  # return a docstring string
```

Configuration in YAML:
```yaml
summarizer:
  callable_path: "mypackage.ai:generate_summary"
  kwargs:
    model: "gpt-4o"
    max_tokens: 100
```

The `kwargs` from YAML are passed as `**kwargs` to the summarizer on every call.

---

#### `parser.py` — The Extraction Engine

This is the largest and most complex file. It ties together the registry, query loader, summarizers, and tree-sitter to produce `SkeletonNode` objects.

**Two public entry points:**

- `extract_skeleton_nodes(directory, *, summarize, config)` — walks an entire directory tree and collects nodes from all supported files. Internally it calls `_iter_supported_files()` (which uses `os.walk` with `exclude_dirs` + layered `.gitignore` filtering) and then calls `extract_file_skeleton_nodes` on each.
- `extract_file_skeleton_nodes(file_path, *, summarize, config)` — processes a single file and returns its nodes. This is the core logic.

**What `_iter_supported_files` does:**

```python
for current_root, dir_names, file_names in os.walk(root, ...):
    # Remove excluded dirs and .gitignore-matched dirs IN-PLACE (top-down prune)
    dir_names[:] = sorted(
        name for name in dir_names
        if name not in config.extraction.exclude_dirs
        and not matches_layered_gitignore(current_root / name)
    )
    for file_name in sorted(file_names):
        if not matches_layered_gitignore(current_root / file_name) and file.suffix in extension_registry:
            yield file
```

Layered `.gitignore` behavior is scoped by directory: root rules apply globally; nested `.gitignore` rules apply only to their subtree; negations are preserved. If `respect_gitignore=False` or no `.gitignore` files are present, traversal behavior matches the previous implementation. The in-place mutation of `dir_names` is the standard Python pattern for pruning `os.walk` traversal. Files and directories are sorted for deterministic ordering.

**The per-file flow in detail:**

```
Step 1: Look up file extension in registry
        → if not found, return [] (unsupported file type, skip silently)

Step 2: Load .scm query text
        → if missing and strict=False, return [] with a warning

Step 3: Build tree-sitter Parser
        ├── _build_parser(language_setting):
        │     import grammar_package
        │     get grammar_factory = getattr(module, grammar_module)
        │     call factory() if callable, else use directly
        │     wrap in Language() if not already
        │     return Parser(language)  ← handles both old and new tree-sitter API
        │
        ├── Success → proceed with tree-sitter
        └── Exception raised:
            ├── If language is Python → fall back to stdlib ast (always available)
            └── If other language:
                ├── strict=True  → re-raise the exception
                └── strict=False → warn and return []

Step 4: Parse source bytes into a tree
        tree = parser.parse(source_bytes)
        → on failure: strict=True raises, strict=False warns and returns []

Step 5: Run the .scm query against the tree root
        query = parser.language.query(query_text)
        captures = query.captures(tree.root_node)
        → _collect_captures normalizes the result:
          tree-sitter has two capture return formats (dict vs list-of-tuples)
          depending on version; this function handles both

Step 6: For each @definition node (sorted by start_byte):
        - Find @signature node whose byte range is inside this definition's range
        - Find @docstring node whose byte range is inside this definition's range
        - If summarize=True and docstring is "" → call summarizer(signature, ...)
        - Append SkeletonNode with start_line/end_line from tree-sitter points
```

**Byte range matching explained:**

Tree-sitter gives every node a `start_byte` and `end_byte`. To find which `@signature` node belongs to which `@definition`, the code checks:
```python
definition.start_byte <= signature_node.start_byte and signature_node.end_byte <= definition.end_byte
```
This means "the signature node is fully contained within the definition node." Same logic applies for docstrings.

**The Python AST fallback (`_extract_python_nodes_with_ast`):**

If the tree-sitter Python grammar can't be built (e.g. C extension not compiled for this platform), Python falls back to `ast.parse()` from the standard library. This always works because `ast` is a pure Python module.

The fallback collects `FunctionDef`, `AsyncFunctionDef`, and `ClassDef` nodes, uses `node.lineno` and `node.end_lineno` for line ranges, and extracts the first statement from the body if it's a string constant (the docstring).

---

### `graph/`

The graph package answers the question: "which definitions depend on which other definitions?" It builds a directed graph where each node is a `SkeletonNode` and each edge means "A imports/calls B."

---

#### `exceptions.py` — Graph Error Types

```python
EdgeLabel = Literal["imports", "calls"]
```

There are only two types of relationships in the graph. `EdgeLabel` being a `Literal` type means the type checker will catch any typo — you can't accidentally create an edge with label `"import"` (missing the s).

```python
@dataclass(frozen=True, slots=True)
class CycleEdge:
    source_node_id: str
    target_node_id: str
    labels: tuple[EdgeLabel, ...]   # which relationship types form this edge

class CycleError(Exception):
    cycle_edges: list[CycleEdge]    # the full cycle path as a list of edges
```

`CycleError` carries the full cycle path so callers can report exactly which definitions form the circular dependency.

---

#### `state.py` — Thread-safe Graph Singleton

The graph is built once at startup and then read by every MCP tool call. Rather than pass it around as a parameter everywhere, it's stored in a module-level singleton protected by a `threading.Lock`.

```python
_STATE_LOCK: Lock = Lock()
_GRAPH = None  # RelationshipGraph | None

def get_graph(): ...    # acquire lock, return _GRAPH
def set_graph(graph): ...  # acquire lock, set _GRAPH
def clear_graph(): ...  # acquire lock, set to None
```

Why use a lock? The MCP server uses the `mcp` library which may handle concurrent tool calls in separate threads. Without the lock, a `set_graph` call during a re-index could race with a `get_graph` call during a search, causing partial reads of a half-built graph.

---

#### `builder.py` — Relationship Graph Construction

This is the most algorithmically interesting file in the codebase.

**What it does, conceptually:**

Given a list of `SkeletonNode` objects, build a directed graph where:
- Each node is one definition (function or class)
- Each edge A → B means "A's signature text references B's name"
- Edges are typed: `"imports"` or `"calls"`

**The node ID format:**

```python
def compute_node_id(node: SkeletonNode) -> str:
    return f"{node.file_path}:{node.start_line}"
```

For example: `/project/auth.py:15`. This is the canonical identity of a node — it tells you exactly where in the codebase to find the definition.

Note: the vector store uses a different ID (SHA-256 hash) for its own storage. The graph and vector store have independent ID schemes because they serve different purposes — the graph ID is human-readable for navigation; the hash ID is stable and URL-safe for database storage.

**`build_graph(nodes)` step by step:**

```
1. Create an empty NetworkX DiGraph.

2. Add each SkeletonNode as a graph node (using its node_id as the key).
   Also build a reverse index: definition_name → [node_id, ...]
   The name is extracted by parsing the raw_signature with stdlib ast.

3. For each node, parse its raw_signature to find references:
   - _extract_reference_names() runs ast.parse on the signature
   - Returns {"imports": {set of names}, "calls": {set of names}}

4. For each referenced name, look it up in the definition index.
   If found, add a directed edge: source_node_id → target_node_id
   with the appropriate label ("imports" or "calls").

5. If both A→B and A→B already exist with different labels,
   _add_edge_label merges them: edge gets labels=("calls", "imports").

6. Call detect_cycles() — uses NetworkX's find_cycle().
   If a cycle exists, raise CycleError with the full cycle path.
```

**Why parse signatures with `ast` again?**

The `raw_signature` is just a line of text like `def verify_token(token: str) -> bool:`. To extract the defined name (`verify_token`) and any references (imports/calls within it), the code normalizes the signature into something `ast.parse` can handle — appending `pass` to make incomplete function stubs valid Python — then uses `ast.walk` to find `Import`, `ImportFrom`, and `Call` nodes.

**What `get_neighbors` returns:**

```python
graph.get_neighbors("/project/auth.py:15")
# returns:
{
    "inbound": [
        {"node_id": "/project/main.py:3", "label": "calls"},
    ],
    "outbound": [
        {"node_id": "/project/jwt.py:22", "label": "imports"},
        {"node_id": "/project/db.py:8",  "label": "calls"},
    ]
}
```

Inbound = "who depends on me". Outbound = "what do I depend on."

**`rebuild(nodes)`** — convenience wrapper that builds the graph and immediately stores it in `graph.state`. This is what the MCP server calls on startup.

---

### `indexing/`

The indexing package turns `SkeletonNode` objects into searchable vector embeddings stored in LanceDB.

---

#### `embedding.py` — Embedding Providers

**Why embeddings?**

A vector embedding is a list of ~3000 floating-point numbers that represent the "meaning" of a piece of text. Two texts that are semantically similar will have vectors that are close together in that high-dimensional space. This lets you do a "meaning search" — ask "find me code that validates tokens" and get back the function `verify_jwt_signature` even though your query didn't contain any of those exact words.

**`EmbeddingProvider` Protocol:**

```python
class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...
```

This is a structural protocol (duck typing) — any class with an `embed` method that takes a string and returns a list of floats qualifies. This makes it easy to swap in a different embedding model without changing any other code.

**`GeminiEmbeddingProvider`:**

The default provider. Uses Google's `gemini-embedding-001` model via the `google-genai` SDK.

API key resolution order (stops at first success):
1. `GEMINI_API_KEY` environment variable
2. Path from `GEMINI_KEY_PATH` environment variable
3. Contents of `.geminikey` file in the current directory

Exponential backoff retry logic (`_retry_with_backoff`):
- On failure, wait `base_delay * 2^(attempt-1)` seconds before retrying
- With defaults: wait 1s, then 2s, then 4s (capped at 8s), giving 3 total attempts
- This handles transient API rate limits or network hiccups

**`build_node_embedding_text(node) -> str`:**

```python
return node.raw_signature + "\n" + node.docstring
```

This is the text that gets converted to a vector. Signature comes first so the function/class name and type information dominate the embedding. The docstring adds semantic context (what the function *does*). If there's no docstring, it's just the signature.

---

#### `vector_store.py` — LanceDB Vector Store

LanceDB is an embedded vector database (like SQLite, but for vectors). It stores data on disk in the `.lancedb` directory and supports approximate nearest-neighbor (ANN) vector search.

**`SkeletonNodeVectorStore` — the table schema:**

| Column | Type | Purpose |
|---|---|---|
| `node_id` | string | SHA-256 of `file_path:start_line` — stable unique identifier |
| `file_path` | string | Original file path for display |
| `start_line` | int64 | Line number for display and `cosk_get_symbol_source` |
| `end_line` | int64 | End line for display |
| `raw_signature` | string | The signature text, returned in search results |
| `summary` | string | The docstring (named `summary` in storage) |
| `vector` | list[float32, dim] | The embedding vector; `dim` fixed at index creation time |

The `node_id` is a SHA-256 hash (not the `path:line` format used in the graph) because it needs to be stable across renames and it needs to be usable as a database key without special character escaping.

**`rebuild_index(nodes)` — full rebuild:**

This method replaces the entire index. It uses a staging table to make the operation as atomic as possible:

```
1. Embed every node (calls GeminiEmbeddingProvider.embed for each)
2. Create a staging table (name = table_name + "__staging")
3. Insert all rows into staging table
4. Drop the old production table
5. Create new production table with same schema
6. Insert all rows again into production table
7. Drop staging table
8. Call validate_index() — crash if schema is wrong
```

Why the staging table? If step 4 or 5 crashes mid-way, the staging table still exists on disk and can be recovered. Without staging, a crash during rebuild would leave the production table deleted with no data inserted yet.

**`upsert_nodes(nodes)` — incremental update:**

For when only some definitions changed (e.g. after editing one file). Uses LanceDB's `merge_insert` operation:
```python
table.merge_insert("node_id")
    .when_matched_update_all()    # existing row: update all columns
    .when_not_matched_insert_all() # new row: insert
    .execute(rows)
```
This is an "upsert" — update if exists, insert if not — keyed on `node_id`.

**`search(query, top_k=5)` — vector similarity search:**

```
1. Validate query is non-empty
2. Embed the query string using the same embedding provider
3. Run ANN (Approximate Nearest Neighbor) search in LanceDB
4. Return top_k results as list[SkeletonNodeSearchResult]
   (strips the vector column — callers don't need the raw floats)
```

The vector dimension must be consistent — you can't search a 3072-dim index with a 768-dim query. `validate_index()` and the upsert/search code all check this.

**`validate_index() -> bool`:**

Checks that the `.lancedb` directory exists, the table can be opened, and all 7 required columns are present in the schema. Returns `True`/`False` without raising. Used by the MCP server at startup to fail fast if the index is missing or corrupt.

---

### `mcp/server.py` — The MCP Server

MCP (Model Context Protocol) is a standard protocol for AI assistants to call external tools. An MCP server communicates over stdin/stdout using JSON messages. The AI assistant sends a tool call request; the server executes it and sends back the result.

Cosk's MCP server exposes 3 tools that together give an AI agent full ability to explore a codebase:

---

#### Tool 1: `cosk_semantic_search`

**Input:** `query_string: str`

**What it does:** Embeds the query, runs vector ANN search in LanceDB, returns the top 5 most semantically similar definitions as JSON.

**Example call:** `cosk_semantic_search("validate JWT token")`

**Example response:**
```json
[
  {
    "node_id": "abc123...",
    "file_path": "/project/auth.py",
    "start_line": 15,
    "end_line": 22,
    "raw_signature": "def verify_jwt_token(token: str) -> bool:",
    "summary": "Validates the JWT token signature and checks expiry."
  },
  ...
]
```

The AI agent uses this to find relevant code without reading all files.

---

#### Tool 2: `cosk_get_neighbors`

**Input:** `node_id: str` (the `file_path:start_line` format)

**What it does:** Looks up the node in the in-memory relationship graph and returns its direct neighbors — both inbound (who calls/imports this) and outbound (what this calls/imports).

**Example call:** `cosk_get_neighbors("/project/auth.py:15")`

**Example response:**
```json
{
  "inbound": [
    {"node_id": "/project/main.py:3",  "label": "calls"},
    {"node_id": "/project/api.py:44",  "label": "calls"}
  ],
  "outbound": [
    {"node_id": "/project/jwt.py:22",  "label": "imports"},
    {"node_id": "/project/db.py:8",    "label": "calls"}
  ]
}
```

The AI agent uses this to trace dependencies — "what would break if I change this function?"

---

#### Tool 3: `cosk_get_symbol_source`

**Input:** `node_ids: list[str]`, optional `index_name: str`

**What it does:** Resolves one or more node IDs to metadata and literal source lines in one call. This is the "drill down" tool — once the AI finds relevant node IDs via search or graph navigation, it can read actual implementations without extra round-trips.

---

#### Startup sequence

```
1. Parse CLI arguments:
   --target-dir   Directory to extract and index (triggers full rebuild on startup)
   --db-dir       Where the LanceDB data lives (default: cosk/.lancedb)

2. Load embedding provider:
   Check COSK_EMBEDDING_PROVIDER_FACTORY env var.
   If set: dynamically import and call the factory function.
   If not set: use GeminiEmbeddingProvider() with default settings.

3a. If --target-dir given:
    - extract_skeleton_nodes(target_dir)  → list[SkeletonNode]
    - rebuild_index(nodes)                → LanceDB populated
    - rebuild(nodes)                      → NetworkX graph built + stored in state

3b. If --target-dir not given:
    - validate_index()                    → crash if index missing/corrupt

4. create_mcp_server(vector_store).run("stdio")
   → blocks forever, reading tool calls from stdin, writing results to stdout
```

**The MCP SDK import conflict fix (`_load_mcp_sdk_modules`):**

Cosk has a subdirectory named `mcp/` (which is the `cosk.mcp` package). Python's import system also needs to load the PyPI `mcp` package (the MCP SDK). These two collide: when Python tries to `import mcp`, it can find cosk's own `mcp/` folder first and import the wrong thing.

The fix: `_load_mcp_sdk_modules()` temporarily removes the cosk package root from `sys.path` before importing the MCP SDK, then restores it. It also evicts any stale `mcp.*` entries from `sys.modules` that point to cosk's folder. This runs once at module load time (the bottom of the file runs it immediately into `mcp_types, FastMCP, McpError`).

**Custom embedding provider via environment variable:**

```bash
COSK_EMBEDDING_PROVIDER_FACTORY=mypackage.testing:make_stub_provider
```

The env var is in `"module:callable"` format. The factory is called with no arguments and must return an object with an `embed(text: str) -> list[float]` method. This is primarily for testing — it lets you plug in a fake embedding provider that returns deterministic vectors without making real API calls.

---

### `safety/`

Currently just a stub package (`__init__.py` with only a docstring). Planned to contain:
- Traversal depth limits (prevent infinite recursion in graph traversal)
- Maximum result count guardrails
- Cycle detection utilities separate from the graph builder

Nothing calls into this package yet.

---

### `tests/`

17 test files covering every module. Key test files and what they verify:

| Test file | What it covers |
|---|---|
| `test_config.py` | YAML loading, `_parse_config`, `enabled` auto-detection |
| `test_models.py` | `SkeletonNode` immutability and field access |
| `test_registry.py` | Extension mapping, duplicate detection |
| `test_query_loader.py` | `.scm` file loading, strict/lenient modes |
| `test_summarizers.py` | `load_summarizer`, noop behavior, bad paths |
| `test_parser_file.py` | Single-file extraction, tree-sitter path |
| `test_parser_dir.py` | Directory walking, exclude dirs, symlink behavior |
| `test_graph_builder.py` | Graph construction, edge labels, cycle detection |
| `test_embedding.py` | `GeminiEmbeddingProvider`, retry logic, key resolution |
| `test_vector_store.py` | `rebuild_index`, `upsert_nodes`, `search`, `validate_index` |
| `test_mcp_server.py` | Tool logic unit tests (mocked store + graph) |
| `test_mcp_server_integration.py` | Full server startup integration test |
| `test_scaffold.py` | Package importability, module structure |
| `test_deps.py` | All declared dependencies are installable |
| `test_installability.py` | `pip install -e .` works cleanly |
| `test_json_schema.py` | `skeleton_nodes_to_json` output shape |

Tests marked `@pytest.mark.integration` install dependencies or run cross-process checks and are slower — run selectively with `pytest -m "not integration"` for fast feedback.

---

## Key Design Decisions

| Decision | Why it matters |
|---|---|
| `SkeletonNode` is `frozen=True, slots=True` | Immutable: safe to put in sets, use as dict keys, share across threads without copies. `slots` saves memory when you have thousands of nodes. |
| `get_cosk_config()` is `@lru_cache` | The YAML file is read exactly once per process. Every call to `build_extension_registry` or `extract_skeleton_nodes` that omits the `config` arg gets the same object — no repeated file I/O. |
| Two-pass graph build (first add all nodes, then add edges) | If you added edges in one pass, a node that appears in a signature reference before it's been added as a node would cause a KeyError or silent miss. Two passes guarantee all nodes exist before any edge lookup. |
| Staging table in `rebuild_index` | Crash-safe: if the process dies mid-rebuild, the staging table can be found and cleaned up. The production table is never left in a half-written state. |
| SHA-256 `node_id` in vector store vs `path:line` in graph | The graph ID is human-readable and useful in tool responses. The vector store ID needs to be stable across file renames for upsert to work correctly. These are different requirements so they use different ID schemes. |
| Python stdlib `ast` fallback | Python is the language most likely to be used in an environment where the C extension grammars don't build (e.g. some ARM or minimal Docker images). The fallback ensures Python always works. |
| `strict=False` default | A codebase may have some languages whose grammars aren't installed. By default, those files are skipped with a warning rather than crashing the whole extraction. `strict=True` is for CI/CD where you want hard failures. |
| MCP SDK path surgery at module import time | If this were deferred to the first tool call, the collision could cause confusing import errors at runtime. Doing it once at module load gives a clear error surface. |
| `EdgeLabel` as a `Literal` type | Prevents silent bugs from typos in edge label strings. The type checker catches `"call"` or `"import"` immediately. |

---

## How to Run

```bash
# Install in editable mode (required before first run)
python -m pip install -e .

# Build/rebuild index only (respects .gitignore by default)
cosk index --target-dir /path/to/your/project

# Start MCP server — reuse an existing index
cosk serve --db-dir /path/to/.lancedb

# Inspect local DB + graph
cosk inspect --db-dir /path/to/.lancedb

# Optional one-run opt-out from .gitignore filtering
cosk index --target-dir /path/to/your/project --no-gitignore

# Backward compatible module entrypoints still work
python -m cosk.mcp.server --target-dir /path/to/your/project
python -m cosk.inspect --db-dir /path/to/.lancedb

# Run all tests
pytest tests/

# Run only fast tests (skip integration)
pytest tests/ -m "not integration"
```

**Required for embeddings:**
```bash
# Option 1: environment variable
export GEMINI_API_KEY=your_key_here

# Option 2: key file
echo "your_key_here" > .geminikey

# Option 3: custom provider (e.g. for testing with no real API)
export COSK_EMBEDDING_PROVIDER_FACTORY=mypackage.stubs:make_stub_provider
```

---

## File Map

```
cosk/
├── config.py                    # Config dataclasses, YAML loader, validator
├── config/
│   └── cosk.settings.yaml       # 23 language definitions + extraction settings
├── extraction/
│   ├── models.py                # SkeletonNode — the universal data type
│   ├── registry.py              # file extension → LanguageSettings lookup table
│   ├── query_loader.py          # loads .scm query files from package resources
│   ├── summarizers.py           # dynamic loader for optional docstring generator
│   ├── parser.py                # main extraction engine (tree-sitter + ast fallback)
│   └── queries/                 # 23 x .scm tree-sitter query files (one per language)
├── graph/
│   ├── exceptions.py            # EdgeLabel type, CycleEdge, CycleError
│   ├── state.py                 # thread-safe module-level graph singleton
│   └── builder.py               # build_graph(), RelationshipGraph, rebuild()
├── indexing/
│   ├── embedding.py             # EmbeddingProvider protocol + GeminiEmbeddingProvider
│   └── vector_store.py          # SkeletonNodeVectorStore (LanceDB-backed)
├── mcp/
│   └── server.py                # FastMCP server, 3 tools, CLI entry point, SDK import fix
├── safety/
│   └── __init__.py              # stub — guardrails not yet implemented
└── tests/                       # 17 test files covering all modules
```
