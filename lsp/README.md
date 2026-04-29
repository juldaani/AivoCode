# lsp — Custom LSP Client for AivoCode

A server-agnostic, config-driven Language Server Protocol (LSP) client built on top of [`lsp-client`](https://pypi.org/project/lsp-client/). Provides an async API for querying symbols, definitions, references, diagnostics, and more.

## Package Structure

| Module | Visibility | Purpose |
|---|---|---|
| `__init__.py` | Public | Re-exports `LspClient`, `LanguageEntry`, `load_config`, `SYMBOL_KIND_NAMES` |
| `client.py` | Public | `LspClient` — the main async LSP client class |
| `config.py` | Public | `LanguageEntry` dataclass + `load_config()` TOML parser |
| `_symbols.py` | Internal | `SYMBOL_KIND_NAMES` — LSP SymbolKind integer → human-readable name |
| `_translate.py` | Internal | Translates `file_watcher` events → LSP `FileEvent` objects |
| `run_tst.py` | Script | Smoke test: connects to basedpyright and prints document symbols |

## Quick Start

```python
from pathlib import Path
from lsp import LspClient, LanguageEntry, load_config

# Option A: load from lsp_config.toml
configs = load_config(Path("lsp_config.toml"))

# Option B: construct manually
entry = LanguageEntry(
    name="python",
    suffixes=(".py", ".pyi"),
    server="basedpyright-langserver",
    server_args=("--stdio",),
)

# Use as async context manager
async with LspClient(lang_entry=entry, workspace=Path.cwd()) as client:
    # Query document symbols
    symbols = await client.request_document_symbol_list(Path("my_module.py"))

    # Check server capabilities before exposing a tool
    if client.supports("definition_provider"):
        defs = await client.request_definition(Path("my_module.py"), position)

    # Get diagnostics (waits for server push if not yet available)
    diags = await client.get_diagnostics(Path("my_module.py"))
```

## Configuration

Configuration is read from `lsp_config.toml` at the repo root. Each language server is a `[[language]]` table:

```toml
[[language]]
name = "python"
suffixes = [".py", ".pyi"]
server = "basedpyright-langserver"
server_args = ["--stdio"]

[[language]]
name = "typescript"
suffixes = [".ts", ".tsx"]
server = "vtsls"
server_args = ["--stdio"]
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Language identifier (must be a valid LSP `LanguageKind`, e.g. `python`, `typescript`, `cpp`) |
| `suffixes` | string list | No | File extensions this server handles (e.g. `[".py", ".pyi"]`) |
| `server` | string | Yes | Server binary on PATH (e.g. `basedpyright-langserver`) |
| `server_args` | string list | No | Arguments passed to the server process (e.g. `["--stdio"]`) |

## LspClient API

`LspClient` is an `attrs`-based class that composes multiple `lsp-client` mixins. Use it as an **async context manager**.

### Request Methods

| Method | Returns | Description |
|---|---|---|
| `request_document_symbol_list(file_path)` | `DocumentSymbol[] \| None` | Symbols in a single file |
| `request_workspace_symbol_list(query)` | `SymbolInformation[] \| None` | Symbols across the workspace |
| `request_definition(file_path, position)` | `Location[] \| None` | Go-to-definition |
| `request_type_definition(file_path, position)` | `Location[] \| None` | Go-to-type-definition |
| `request_references(file_path, position)` | `Location[] \| None` | Find all references |
| `request_hover(file_path, position)` | `Hover \| None` | Hover information |
| `request_call_hierarchy_incoming_call(file_path, position)` | `CallHierarchyIncomingCall[] \| None` | Incoming calls |
| `request_call_hierarchy_outgoing_call(file_path, position)` | `CallHierarchyOutgoingCall[] \| None` | Outgoing calls |
| `request_rename(file_path, position, new_name)` | `WorkspaceEdit \| None` | Rename symbol |

### Custom Methods

| Method | Returns | Description |
|---|---|---|
| `get_diagnostics(file_path, timeout=5.0)` | `Diagnostic[]` | Get diagnostics for a file; waits up to `timeout` seconds for the server |
| `supports(capability)` | `bool` | Check if the server advertises a given capability (e.g. `"definition_provider"`) |
| `notify_file_changes(batch)` | `None` | Translate a `WatchBatch` and send `didChangeWatchedFiles` (filtered by suffixes) |
| `shutdown()` | `None` | Gracefully shut down the server (sends `shutdown` + `exit`) |

### Attributes

| Attribute | Type | Description |
|---|---|---|
| `lang_entry` | `LanguageEntry` | Configuration for this language server |
| `server_capabilities` | `ServerCapabilities \| None` | Available after entering the context manager |

## SymbolKind Lookup

`SYMBOL_KIND_NAMES` maps LSP `SymbolKind` integers (1–26) to human-readable names:

```python
from lsp import SYMBOL_KIND_NAMES

SYMBOL_KIND_NAMES[5]   # "Class"
SYMBOL_KIND_NAMES[12]  # "Function"
```

## Dependencies

- [`lsp-client`](https://pypi.org/project/lsp-client/) — underlying LSP protocol library
- [`attrs`](https://pypi.org/project/attrs/) — class definition for `LspClient`
- [`file_watcher`](../file_watcher/) — sibling package providing `WatchBatch` / `WatchEvent` types
