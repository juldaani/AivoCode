# cli

Thin UI layer for aivoCode tools. All processing lives in the corresponding packages — the CLI only parses arguments, calls the public API, and prints the result.

## Commands

```
python -m cli lsp <file> --symbols
python -m cli webfetch <url> [options]
python -m cli websearch <query> [options]
```

Each worktree runs its own CLI code via `python -m cli` — no global `aivocode` install needed.

## Options

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
