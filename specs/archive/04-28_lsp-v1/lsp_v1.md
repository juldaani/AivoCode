# LSP v1 Specification

## Overview

A language-server-agnostic LSP client that connects to one or more language servers
for codebase exploration. Designed for MCP server integration (not implemented here).

Key design decisions:
- Server-agnostic: any `--stdio` LSP server works, configured via TOML
- Multi-language: one LspClient instance per language, routed by file suffix
- File watcher integration: LspClient accepts WatchBatch internally, translates
  to didChangeWatchedFiles notifications
- Upstream orchestration: MCP (or other upstream) owns the event loop, starts/stops
  clients, calls query methods


## Architecture

```
  UPSTREAM (MCP server or other orchestrator)
  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │  ┌─────────────┐    ┌──────────────────────────────────┐   │
  │  │ file_watcher│    │      LspClient (per language)     │   │
  │  │             │    │                                  │   │
  │  │  WatchBatch ├───►│  notify_file_changes(batch)  ────┼──►│ LSP Server
  │  │             │    │  (filters by suffix, translates   │   │ (basedpyright,
  │  │             │    │   internally, sends didChange...) │   │  typescript-..., etc)
  │  │             │    │                                  │   │
  │  │             │    │  open_files(f) ─► request ─► close│   │
  │  │             │    │  (didOpen → documentSymbol ──────┼──►│
  │  │             │    │   / references → didClose)        │   │
  │  └─────────────┘    │                                  │   │
  │                      │  server_capabilities (stored)    │   │
  │                      └──────────────────────────────────┘   │
  └─────────────────────────────────────────────────────────────┘
```


## Module Layout

```
lsp/
├── __init__.py        # Package exports: LspClient, LanguageEntry, load_config
├── client.py          # LspClient (mixin-based, server-agnostic via config)
│                        - notify_file_changes(batch) — internal translation
│                        - open_files → request → close pattern
│                        - Stores server_capabilities post-init
├── config.py          # LanguageEntry dataclass + TOML loader
│                        - load_config(path) → list[LanguageEntry]
│                        - Auto-detect languages from workspace
├── _symbols.py        # SYMBOL_KIND_NAMES: dict[int, str] — LSP spec enum
│                        - Kind number → human-readable name for MCP output
│                        - Internal module, also used by tests
├── _translate.py      # Internal: WatchEvent → LSP FileEvent translation
│                        - Not exported from package
│                        - Pure data transformation, no I/O
└── run_tst.py         # Smoke test (existing)
```


## Config File

Location: `lsp_config.toml` at repo root.

```toml
[[language]]
name         = "python"                        # LanguageKind value (maps to LSP LanguageId)
suffixes     = [".py", ".pyi"]                 # File extensions this server handles
server       = "basedpyright-langserver"       # Binary on PATH
server_args  = ["--stdio"]                     # Server transport arguments
project_files = ["pyproject.toml", "setup.py", "setup.cfg"]  # Root detection markers
exclude      = [".venv/**", "venv/**"]          # Exclude from project detection

[[language]]
name         = "typescript"
suffixes     = [".ts", ".tsx"]
server       = "typescript-language-server"
server_args  = ["--stdio"]
project_files = ["tsconfig.json", "package.json"]
exclude      = ["node_modules/**"]
```

### LanguageEntry dataclass

```python
@dataclass(frozen=True, slots=True)
class LanguageEntry:
    """One language server configuration from lsp_config.toml."""
    name: str                              # e.g. "python" → LSP LanguageId
    suffixes: tuple[str, ...]              # e.g. (".py", ".pyi")
    server: str                            # e.g. "basedpyright-langserver"
    server_args: tuple[str, ...]           # e.g. ("--stdio",)
    project_files: tuple[str, ...]         # e.g. ("pyproject.toml",)
    exclude: tuple[str, ...]              # e.g. (".venv/**",)
```


## LspClient API

```python
class LspClient(Client, WithRequestDocumentSymbol, WithRequestReferences):
    """
    Server-agnostic LSP client.

    Constructed from a LanguageEntry and workspace path:
        config = LanguageEntry(name="python", ...)
        client = LspClient(lang=config, workspace=Path.cwd())
        async with client:
            ...
    """

    # Lifecycle (inherited from Client, handled by lsp-client)
    # - async with LspClient(...) connects, initializes, shuts down

    # File change notification (NEW — our addition)
    async def notify_file_changes(self, batch: WatchBatch) -> None:
        """
        Translate file_watcher WatchBatch to didChangeWatchedFiles notification.

        Filters events by this client's file suffixes (from LanguageEntry).
        Only sends events matching this language. No-op if no matching events.
        Internally translates WatchEvent.change → FileChangeType and
        WatchEvent.abs_path → file:// URI.
        """

    # On-demand queries (from lsp-client mixins)
    async def open_files(*paths) -> AsyncContextManager:
        """Open files for tracking. Sends didOpen. Use as context manager."""

    async def request_document_symbol_list(path) -> Sequence[DocumentSymbol] | None:
        """Request hierarchical document symbols for a file."""

    async def request_references(path, position, ...) -> Sequence[Location] | None:
        """Request references for a symbol at position in a file."""

    # Server capabilities (stored post-init, ready for future use)
    server_capabilities: ServerCapabilities | None
        """
        Server capabilities received during initialization.
        Stored for future use (capability checks, feature detection).
        Accessible but not acted on in v1.
        """
```

### Upstream Usage Pattern

```python
# Load config, create clients
configs = load_config(workspace_root / "lsp_config.toml")
clients = {}
for cfg in configs:
    clients[cfg.name] = LspClient(lang=cfg, workspace=workspace_root)

# Start all clients
for client in clients.values():
    await client.__aenter__()  # or use async context manager

# File watcher loop — each client filters by its suffixes
async for batch in awatch_repos([workspace_root], watch_config):
    for client in clients.values():
        await client.notify_file_changes(batch)

# On-demand query (e.g. MCP tool call)
async def get_symbols(file_path: Path, language: str):
    client = clients[language]
    async with client.open_files(file_path):
        return await client.request_document_symbol_list(file_path)

# Shutdown
for client in clients.values():
    await client.__aexit__(None, None, None)
```


## Translation Logic (`_translate.py`)

Internal module, not exported. Pure data transformation.

### WatchEvent.change → FileChangeType mapping

```
Watchfiles Change.added    → FileChangeType.Created  (1)
Watchfiles Change.modified  → FileChangeType.Changed  (2)
Watchfiles Change.deleted   → FileChangeType.Deleted  (3)
```

### Path → URI conversion

```
WatchEvent.abs_path (Path) → file:///absolute/path/to/file.py (URI)
```

Uses `Path.as_uri()` from the standard library (same as existing helpers.py).

### Suffix filtering

```
LanguageEntry.suffixes = (".py", ".pyi")
WatchEvent.rel_path = "src/main.py"  → matches ".py"  → INCLUDE
WatchEvent.rel_path = "README.md"    → no match        → EXCLUDE
```

Each LspClient only processes events whose file suffix matches its LanguageEntry.suffixes.

### LSP SymbolKind Reference (Spec-Defined, Universal)

Every LSP-compliant server uses these exact values. From the LSP 3.17 spec:

```
 1 = File           10 = Enum          19 = Object
 2 = Module         11 = Interface     20 = Key
 3 = Namespace       12 = Function      21 = Null
 4 = Package         13 = Variable      22 = EnumMember
 5 = Class           14 = Constant      23 = Struct
 6 = Method          15 = String        24 = Event
 7 = Property        16 = Number        25 = Operator
 8 = Field           17 = Boolean       26 = TypeParameter
 9 = Constructor     18 = Array
```

What varies between servers is **which kind they assign** to a given symbol
(e.g. one server may classify a module-level constant as Constant (14), another
as Variable (13)). The enum values themselves never change.

This mapping lives in `lsp/_symbols.py` as `SYMBOL_KIND_NAMES: dict[int, str]`
so that kind numbers can be translated to human-readable names before returning
through MCP or any other interface.

Usage: `SYMBOL_KIND_NAMES[5]` → `"Class"`, `SYMBOL_KIND_NAMES[12]` → `"Function"`


## Server Capabilities

After initialization, the LSP server sends its capabilities in the `InitializeResult`.
These are stored on the LspClient instance for future use:

```python
# Accessible after async with LspClient(...) completes
client.server_capabilities  # ServerCapabilities object from lsp_client
```

v1 does not act on these capabilities beyond validation (already handled by lsp-client).
Future: check capabilities before making requests, dynamic feature enablement.


## File Sync Flow

### On-demand query (documentSymbol, references)

```
1. Upstream opens file:      async with client.open_files(file_path):
2. Client sends:             textDocument/didOpen (file content from disk)
3. Upstream makes request:   result = await client.request_document_symbol_list(path)
4. Context manager exits:    textDocument/didClose
```

### Background file changes (from file_watcher)

```
1. file_watcher yields WatchBatch
2. Upstream calls:           await client.notify_file_changes(batch)
3. Client internally:
   a. Filters events by suffix
   b. Translates WatchEvent → FileEvent (uri, change_type)
   c. Sends:                  workspace/didChangeWatchedFiles notification
4. Server re-indexes affected files from disk
```


## Testing

### Test Data

```
tests/data/mock_repos/
├── python/
│   ├── pyproject.toml
│   └── mock_pkg/
│       ├── __init__.py
│       ├── utils.py          # Existing, used for documentSymbol tests
│       └── utils_tests_gt.json  # Generic GT (schema_version 2, kind_legend)
└── typescript/
    ├── tsconfig.json
    └── mock_pkg/
        ├── index.ts           # Basic TypeScript file for multi-lang tests
        └── helpers.ts         # Additional file for references tests
```

### Testing Approach

The LSP spec defines a **fixed SymbolKind enum** (values 1–26). Every compliant
server uses the same numbers — Class is always 5, Function is always 12, etc.

Tests use `SYMBOL_KIND_NAMES` from `lsp/_symbols.py` to translate kind numbers
to human-readable names, and assert on those names directly. Mainstream servers
classify symbols consistently (classes are Class, functions are Function, etc.),
so generic assertions work without per-server GT files.

**Generic assertions (server-agnostic):**
- documentSymbol returns a non-empty list for a non-trivial file
- Symbol names match expected function/class names
- Symbol kinds map to expected names via SYMBOL_KIND_NAMES
  - e.g. `Greeter` → kind 5 → "Class"
  - e.g. `hello` → kind 12 → "Function" (or kind 6 → "Method" if inside a class)
- Hierarchy: children appear under parent symbols
- request_references returns results for a known symbol reference
- notify_file_changes does not raise errors with valid WatchBatch data
- Multi-language: Python client processes .py events, TS client processes .ts events

**NOT in v1 tests:**
- Per-server GT JSON files
- Assertions on exact nesting depth (varies by server)


## v1 Scope

### In scope

- LspClient with DocumentSymbol + References capabilities
- Server-agnostic config via LanguageEntry + TOML
- Multi-language support (one client per language, suffix routing)
- notify_file_changes(WatchBatch) → didChangeWatchedFiles
- open_files → request → close pattern
- Server capabilities stored for future use
- TypeScript mock repo for multi-language testing
- Generic, server-agnostic test assertions

### Not in scope (deferred)

- MCP server implementation
- hover, definition, completion, code actions, diagnostics
- Incremental text sync (Full only — we're not an editor)
- Custom per-server initialization options beyond config
- Dynamic capability registration handling