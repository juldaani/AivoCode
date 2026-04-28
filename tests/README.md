# Test Suite

This directory contains the full test suite for AivoCode. Tests are organized by scope and use
`pytest` as the runner.

## Quick Start

```bash
# Run everything
pytest

# Run a specific file
pytest tests/unit/lsp/test_client.py

# Run a single test
pytest tests/unit/lsp/test_client.py::TestLspClient::test_initialization

# Run by keyword
pytest -k "diagnostics"
```

## Directory Layout

```
tests/
├── conftest.py              # Shared pytest fixtures (see below)
├── lsp_test.toml           # LSP server config used by integration tests
├── data/                   # Mock repos, fixtures, and test data
│   └── mock_repos/
│       ├── python/         # Minimal Python package for LSP / watcher tests
│       └── typescript/     # Minimal TS project for LSP tests
├── unit/                   # Fast, isolated unit tests
│   ├── lsp/               # LspClient, translation, symbols, config parsing
│   └── file_watcher/      # Gitignore parsing, filter logic
├── integration/            # Tests that hit real external processes
│   ├── lsp/               # Full LSP capability tests (hover, defs, refs, …)
│   │   └── conftest.py    # LSP-specific fixtures (server startup, cleanup)
│   └── file_watcher/      # End-to-end file-watcher scenarios
└── e2e/                    # Broad end-to-end workflows
    └── test_lsp_bridge.py # LSP bridge / server round-trips
```

## Shared Fixtures (`conftest.py`)

- **`mock_python_repo`** — `Path` to the mock Python repo under `data/mock_repos/python`.
- **`sample_watch_event`** — Factory that builds `WatchEvent` objects for file-watcher tests.

## Ground-Truth Testing Philosophy

All LSP integration tests validate server responses against **ground-truth (GT) data**,
not ad-hoc magic numbers or vague "something came back" checks.

### How it works

1. **GT files** live alongside the mock source files and are **server-specific**:
   `mock_pkg/utils.py ←→ mock_pkg/utils_tests_gt_basedpyright.json`
2. The GT filename pattern is `{stem}_tests_gt_{gt_suffix}.json` where `gt_suffix`
   matches the `gt_suffix` field in `lsp_test.toml` (e.g. `basedpyright`, `vtsls`).
   This allows different servers for the same language to have different expected results.
3. Each GT file defines expected results for document symbols, hover, call hierarchy,
   references, definitions, type definitions, rename, and diagnostics.
4. Tests load GT via `lang.load_gt(source_file)` which resolves
   `{stem}_tests_gt_{gt_suffix}.json` automatically based on the configured server.
5. Symbol kind names come from `lsp._symbols.SYMBOL_KIND_NAMES`, not duplicated in GT.

### Why GT data

Without ground truth, tests drift toward "assert something came back" which passes even when
the LSP server returns garbage. GT data anchors every assertion to a known-correct expected
value, making regressions immediately visible.

### Adding a new GT field

1. Add the field to the relevant `*_tests_gt_{gt_suffix}.json` file(s) for **all** servers.
2. Bump `schema_version` if the structure changes.
3. Add a validation check in `tests/unit/lsp/test_symbols.py::TestGroundTruthConsistency`.
4. Update integration tests to use the new GT field.

### GT Schema (version 3)

GT files are named `{source_stem}_tests_gt_{gt_suffix}.json` where `gt_suffix`
corresponds to the `gt_suffix` field in `lsp_test.toml`. For example:

```
mock_pkg/utils_tests_gt_basedpyright.json   # Python + basedpyright
mock_pkg/types_tests_gt_vtsls.json           # TypeScript + vtsls
```

This allows adding a new server for the same language (e.g. `pyright`) by creating
a new `*_gt_pyright.json` file alongside the existing ones, without modifying the
shared mock source files.

```json
{
  "schema_version": 3,
  "source": "mock_pkg/utils.py",
  "symbols": [
    { "name": "Greeter", "kind_category": "Class", "children": [...] }
  ],
  "hover": {
    "create_def": { "must_contain": ["create_and_greet"] }
  },
  "call_hierarchy": {
    "full_def": { "must_include_callees": ["create_and_greet", "process_greeting"] }
  },
  "references": {
    "create_def": { "min_count": 2 }
  },
  "definitions": {
    "greet_call": { "target_file": "types.py", "target_name_contains": "greet" }
  },
  "type_definitions": {
    "greeter_var": { "target_file": "types.py", "target_name_contains": "TypeGreeter" }
  },
  "rename": {
    "create_def": { "new_name": "renamed_create_and_greet", "min_edits": 2 }
  },
  "diagnostics": {
    "min_errors": 5,
    "must_include_message_patterns": ["not assignable to", "is not defined"]
  }
}
```

Not every GT file needs every section — diagnostics GT only has `diagnostics`,
and helpers GT files may only have `symbols`. The `kind_legend` field was removed in
schema v3; test code validates `kind_category` strings against `SYMBOL_KIND_NAMES`
instead.

## LSP Integration Tests

The integration LSP tests spin up real language servers. The list of servers and repos is
defined in `lsp_test.toml`:

| Language   | Server                     | gt_suffix     | Args        | Mock repo    |
|------------|----------------------------|---------------|-------------|--------------|
| Python     | `basedpyright-langserver`  | `basedpyright`| `--stdio`   | `python`     |
| TypeScript | `vtsls`                    | `vtsls`       | `--stdio`   | `typescript` |

Each language gets parametrized automatically. The `gt_suffix` field determines which
ground-truth JSON files are loaded for each server (see GT Schema above).

**To add a new language server** (e.g. `pyright` for Python):
1. Add a new `[[language]]` entry in `lsp_test.toml` with a unique `gt_suffix`.
2. Create `*_tests_gt_{gt_suffix}.json` files in the mock repo for that server.
3. Add a validation check in `TestGroundTruthConsistency` if needed.

**Note:** If the configured language server is not on PATH, the test fails with an error
message rather than silently skipping. This prevents CI from showing all green without
actually running any LSP tests.

## Conventions

- **One `__init__.py` per package** — keeps imports explicit and allows package-level fixtures.
- **No production secrets** — all credentials or keys live in mock data only.
- **Keep unit tests fast** — anything that starts a subprocess belongs in `integration/` or `e2e/`.
- **GT-driven assertions** — LSP integration tests must assert against GT data, not magic
  numbers or `is not None` checks.
