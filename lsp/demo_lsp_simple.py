#!/usr/bin/env python3 -u
"""Minimal demo: LSP query + file watcher + bridge.

    python scripts/demo_lsp.py [path/to/repo]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_watcher import WatchConfig, awatch_repos
from lsp import LspClient, LanguageEntry

WORKSPACE = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path(__file__).resolve().parent.parent
    / "tests" / "data" / "mock_repos" / "python"
)
FILE = WORKSPACE / "mock_pkg" / "utils.py"


async def main() -> None:
    # --- 1. LSP: init, query, print ----------------------------------------
    entry = LanguageEntry(
        name="python", suffixes=(".py", ".pyi"),
        server="basedpyright-langserver", server_args=("--stdio",),
    )

    async with LspClient(lang_entry=entry, workspace=WORKSPACE) as client:
        symbols = await client.request_document_symbol_list(FILE)

        for s in symbols or []:
            print(f"[lsp] {s.name} [{s.kind}]")

        # --- 2. File watcher: watch for changes, forward to LSP ----------
        print("\n[lsp+watcher] watching for .py changes (Ctrl-C to stop) ...\n")
        async for batch in awatch_repos([WORKSPACE], WatchConfig()):
            for ev in batch.events:
                print(f"[watcher] {ev.change.name:8s} {ev.rel_path}")
            # Bridge: tell LSP server about the changes.
            await client.notify_file_changes(batch)


if __name__ == "__main__":
    asyncio.run(main())
