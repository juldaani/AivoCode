"""Test script for lsp-client library with basedpyright.

What this file provides
- Basic test of lsp-client library functionality.
- Uses BasedpyrightClient with explicit server configuration.
- Tests request_document_symbol() on a Python file in this repo.

Why this exists
- Prototype/test code to explore lsp-client API and behavior.
"""

from __future__ import annotations

import anyio
from pathlib import Path

from lsp_client import BasedpyrightClient, LocalServer


# =============================================================================
# Configuration
# =============================================================================

# Workspace root = this repo
REPO_ROOT = Path(__file__).parent.parent.resolve()

# Target file to analyze (relative to repo root)
TARGET_FILE = REPO_ROOT / "lsp_server" / "client.py"

# Explicit server configuration
# Note: basedpyright uses 'basedpyright-langserver' for LSP mode, not 'basedpyright'
SERVER = LocalServer(
    program="basedpyright-langserver",
    args=["--stdio"],
)


# =============================================================================
# Main Test
# =============================================================================


async def main() -> None:
    """Run lsp-client test: connect to basedpyright, request document symbols."""
    print("=" * 60)
    print("lsp-client Test Script")
    print("=" * 60)
    print(f"Repo root: {REPO_ROOT}")
    print(f"Target file: {TARGET_FILE}")
    print(f"Server: basedpyright --stdio")
    print()

    # Create client with explicit server config
    # workspace parameter accepts a Path (single root) or mapping (multi-root)
    # Increase timeout for initialization (basedpyright can be slow on first run)
    client = BasedpyrightClient(
        server=SERVER,
        workspace=REPO_ROOT,
        request_timeout=30.0,
    )

    print("Starting basedpyright server...")
    async with client:
        print("Server started and initialized.\n")

        # Open the target file (sends textDocument/didOpen to server)
        # open_files is an async context manager
        print(f"Opening file: {TARGET_FILE}")
        async with client.open_files(TARGET_FILE):
            print("File opened.\n")

            # Request document symbols
            print("Calling request_document_symbol()...")
            symbols = await client.request_document_symbol(TARGET_FILE)

            print(f"Received {len(symbols) if symbols else 0} symbols:\n")

            if symbols:
                for sym in symbols:
                    # Symbol types: 1=File, 2=Module, 3=Namespace, 4=Package,
                    # 5=Class, 6=Method, 7=Property, 8=Field, 9=Constructor,
                    # 10=Enum, 11=Interface, 12=Function, 13=Variable, etc.
                    kind_name = _symbol_kind_name(sym.kind) if hasattr(sym, "kind") else "?"
                    name = sym.name if hasattr(sym, "name") else str(sym)
                    range_info = ""
                    # DocumentSymbol has 'range' directly, SymbolInformation has 'location.range'
                    if hasattr(sym, "range"):
                        r = sym.range
                        range_info = f" [L{r.start.line}:C{r.start.character}-L{r.end.line}:C{r.end.character}]"
                    elif hasattr(sym, "location"):
                        r = sym.location.range
                        range_info = f" [L{r.start.line}:C{r.start.character}-L{r.end.line}:C{r.end.character}]"
                    print(f"  [{kind_name}] {name}{range_info}")
            else:
                print("  (no symbols returned)")

        print("\nFile closed.")

    print("\nServer shutdown complete.")


def _symbol_kind_name(kind: int) -> str:
    """Convert LSP SymbolKind integer to human-readable name."""
    kinds = {
        1: "File",
        2: "Module",
        3: "Namespace",
        4: "Package",
        5: "Class",
        6: "Method",
        7: "Property",
        8: "Field",
        9: "Constructor",
        10: "Enum",
        11: "Interface",
        12: "Function",
        13: "Variable",
        14: "Constant",
        15: "String",
        16: "Number",
        17: "Boolean",
        18: "Array",
        19: "Object",
        20: "Key",
        21: "Null",
        22: "EnumMember",
        23: "Struct",
        24: "Event",
        25: "Operator",
        26: "TypeParameter",
    }
    return kinds.get(kind, f"Kind{kind}")


if __name__ == "__main__":
    anyio.run(main)
