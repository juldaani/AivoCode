# cli

Thin UI layer for aivoCode tools. The CLI parses arguments and sends HTTP
requests to the REST API server — all processing happens server‑side. Each
worktree runs its own CLI code via `python -m cli`; no global install needed.

## Commands

```
python -m cli lsp symbols <file> [--workspace PATH]
python -m cli lsp start [--workspace PATH]
python -m cli lsp stop [--workspace PATH]
python -m cli lsp status [--workspace PATH]
python -m cli webfetch <url> [options]
python -m cli websearch <query> [options]
```

The CLI connects to the REST API at `$AIVOCODE_URL` (defaults to
`http://localhost:8000`).

## Flags

### lsp

All lsp subcommands accept `--workspace PATH` (override git‑based detection).

### webfetch / websearch

| Flag | Purpose |
|---|---|
| `--heading TEXT` | Extract a section by heading (repeatable) |
| `--line-range N-M` | Extract lines from the cached page (repeatable) |
| `--navigation` | Include page links (internal/external) |
| `--js-render` | Wait for JS-heavy SPAs to settle |
| `--wait-until` | `load` (default), `domcontentloaded`, or `networkidle` |
| `--refresh-cache` | Bypass cache, always fetch fresh |
| `--pretty-format` | Pretty-print the ToC for human readability |
| `--verbose` / `-v` | Status messages to stderr |

## Adding a command

1. Create `cli/commands/<name>.py` with `add_subparser()` and `handle()`
2. Import and register it in `cli/main.py`
