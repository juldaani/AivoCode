#!/usr/bin/env python3
"""Smoke test: connect to basedpyright LSP, fetch documentSymbol, print to stdout.

What this script does
- Starts basedpyright-langserver via lsp-client.
- Connects using LspClient with a LanguageEntry config.
- Opens tests/data/mock_repos/python/mock_pkg/utils.py.
- Requests textDocument/documentSymbol.
- Pretty-prints the symbol hierarchy to stdout.

Why this exists
- Validates that lsp-client + basedpyright work in our environment.
- Tests the new config-driven LspClient API.
- Produces reference output for designing the lsp/ package.

Usage
    python -m lsp.run_tst

Requires
    - lsp-client installed (pip install lsp-client)
    - basedpyright installed and on PATH (pip install basedpyright)
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio

# Repo root is the parent directory of the lsp/ package.
REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_REPO = REPO_ROOT / "tests" / "data" / "mock_repos" / "python"
TARGET_FILE = MOCK_REPO / "mock_pkg" / "utils.py"

# LSP SymbolKind numeric values (subset used by Python servers).
_SYMBOL_KIND_NAMES: dict[int, str] = {
    1: "File",
    2: "Module",
    3: "Namespace",
    4: "Package",
    5: "Class",
    6: "Method",
    7: "Property",
    8: "Field",
    9: "Interface",
    10: "Function",
    11: "Variable",
    12: "Constant",
    13: "String",
    14: "Number",
    15: "Boolean",
    16: "Array",
    17: "Object",
    18: "Key",
    19: "Null",
    20: "EnumMember",
    21: "Struct",
    22: "Event",
    23: "Operator",
    24: "TypeParameter",
}


def _kind_name(kind: int) -> str:
    """Return human-readable name for an LSP SymbolKind integer."""
    return _SYMBOL_KIND_NAMES.get(kind, f"Kind({kind})")


def _print_symbol(sym: object, *, indent: int = 0) -> None:
    """Recursively print a DocumentSymbol with indentation."""
    name = getattr(sym, "name", None) or (sym.get("name") if isinstance(sym, dict) else None) or "?"
    kind = getattr(sym, "kind", None) or (sym.get("kind") if isinstance(sym, dict) else None) or 0
    kind_label = _kind_name(kind) if isinstance(kind, int) else str(kind)

    range_info = getattr(sym, "range", None) or (sym.get("range") if isinstance(sym, dict) else None)
    range_str = ""
    if range_info is not None:
        start = getattr(range_info, "start", None) or (range_info.get("start") if isinstance(range_info, dict) else None)
        end = getattr(range_info, "end", None) or (range_info.get("end") if isinstance(range_info, dict) else None)
        if start and end:
            s_line = getattr(start, "line", start.get("line", "?") if isinstance(start, dict) else "?")
            e_line = getattr(end, "line", end.get("line", "?") if isinstance(end, dict) else "?")
            range_str = f"  L{s_line}-{e_line}"

    prefix = "  " * indent
    children_attr = getattr(sym, "children", None)
    if children_attr is None and isinstance(sym, dict):
        children_attr = sym.get("children")

    print(f"{prefix}{name} [{kind_label}]{range_str}")

    if children_attr:
        for child in children_attr:
            _print_symbol(child, indent=indent + 1)


async def main() -> None:
    """Connect to basedpyright, fetch documentSymbol for utils.py, print results."""
    from lsp import LspClient, LanguageEntry

    print("=" * 60)
    print("LSP Smoke Test: LspClient + basedpyright-langserver")
    print("=" * 60)
    print(f"  Workspace : {MOCK_REPO}")
    print(f"  Target file: {TARGET_FILE}")
    print(f"  File exists: {TARGET_FILE.exists()}")
    print()

    if not TARGET_FILE.exists():
        print(f"ERROR: Target file not found: {TARGET_FILE}", file=sys.stderr)
        sys.exit(1)

    entry = LanguageEntry(
        name="python",
        suffixes=(".py", ".pyi"),
        server="basedpyright-langserver",
        server_args=("--stdio",),
    )

    async with LspClient(lang_entry=entry, workspace=MOCK_REPO) as client:
        print("LSP client connected.\n")
        print(f"Server capabilities: {type(client.server_capabilities).__name__}")
        print()

        print("Requesting documentSymbol...\n")
        symbols = await client.request_document_symbol_list(TARGET_FILE)

        if symbols is None:
            print("No symbols returned (server returned None).")
            return

        print(f"Got {len(symbols)} top-level symbols:\n")
        for sym in symbols:
            _print_symbol(sym, indent=0)

    print("\n" + "=" * 60)
    print("LSP client shut down. Smoke test complete.")


if __name__ == "__main__":
    anyio.run(main)
