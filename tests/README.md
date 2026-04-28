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

## LSP Integration Tests

The integration LSP tests spin up real language servers. The list of servers and repos is
defined in `lsp_test.toml`:

| Language   | Server                     | Args        | Mock repo    |
|------------|----------------------------|-------------|--------------|
| Python     | `basedpyright-langserver`  | `--stdio`   | `python`     |
| TypeScript | `vtsls`                    | `--stdio`   | `typescript` |

Each language gets parametrized automatically, so adding a new entry in the TOML is usually
enough to extend coverage.

## Conventions

- **One `__init__.py` per package** — keeps imports explicit and allows package-level fixtures.
- **No production secrets** — all credentials or keys live in mock data only.
- **Keep unit tests fast** — anything that starts a subprocess belongs in `integration/` or `e2e/`.
