"""One-off vtsls documentSymbol probe through this repo's LspClient.

This intentionally uses `lsp/client.py` and the `lsp-client` Python package path
instead of hand-written JSON-RPC.  Compare with
`test_document_symbol_vtsls.py`, which talks to `vtsls --stdio` directly.

Run from the repository root:
    python typescript_lsp_tst/test_document_symbol_repo_client.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "tests" / "data" / "mock_repos" / "typescript"
TARGET = WORKSPACE / "mock_pkg" / "index.ts"

# Running `python typescript_lsp_tst/script.py` puts typescript_lsp_tst/ on
# sys.path, not the repository root.  Add the root explicitly so this probe uses
# the local lsp/client.py implementation under test.
sys.path.insert(0, str(ROOT))

from lsp import LspClient  # noqa: E402
from lsp.config import LanguageEntry  # noqa: E402


def describe_symbol(symbol: object, indent: int = 0) -> None:
    """Print a minimal view of the lsp-client DocumentSymbol object."""
    prefix = "  " * indent
    name = getattr(symbol, "name", "<no name>")
    kind = getattr(symbol, "kind", "<no kind>")
    selection_range = getattr(symbol, "selection_range", None)
    print(f"{prefix}- {name!r} kind={kind!r} selection_range={selection_range!r}")

    children = getattr(symbol, "children", None) or []
    for child in children:
        describe_symbol(child, indent + 1)


async def main() -> int:
    if not WORKSPACE.exists() or not TARGET.exists():
        print(f"missing workspace or target: {WORKSPACE} / {TARGET}")
        return 2

    entry = LanguageEntry(
        name="typescript",
        suffixes=(".ts",),
        server="vtsls",
        server_args=("--stdio",),
    )
    try:
        print("STARTING LspClient with vtsls --stdio")
        async with LspClient(lang_entry=entry, workspace=WORKSPACE) as client:
            print("INITIALIZED")
            print("server_capabilities:", client.server_capabilities)
            print("document_symbol_provider:", client.supports("document_symbol_provider"))

            print(f"OPEN + documentSymbol: {TARGET}")
            async with client.open_files(TARGET):
                symbols = await client.request_document_symbol_list(TARGET)

            print("RAW SYMBOLS:", symbols)
            if symbols is None:
                print("documentSymbol returned None")
                return 1

            print(f"documentSymbol returned {len(symbols)} top-level symbols")
            for symbol in symbols:
                describe_symbol(symbol)

        return 0 if len(symbols) > 0 else 1
    except TimeoutError:
        print("TIMEOUT: LspClient did not complete the operation in time")
        traceback.print_exc()
        return 1
    except BaseException:
        print("ERROR: LspClient documentSymbol probe failed")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
