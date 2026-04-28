#!/usr/bin/env python3
"""E2E smoke test: LSP client + file watcher integration.

What this script does
- Phase 1: Start basedpyright, open utils.py, print document symbols.
- Phase 2: Run file watcher, create/modify/delete a temp .py file,
  print file change events to stdout.
- Phase 3: Create a new .py file, notify LSP via the bridge, open it,
  print its symbols — proves file changes propagated to the server.

Usage
    python scripts/smoke_lsp.py

Requires
    - lsp-client installed
    - basedpyright-langserver on PATH
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# This script lives in scripts/ and imports from repo-root packages
# (file_watcher, lsp). Add the repo root so imports resolve regardless
# of the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchfiles import Change

from file_watcher import WatchConfig, awatch_repos
from file_watcher.types import WatchBatch, WatchEvent
from lsp import SYMBOL_KIND_NAMES, LspClient, LanguageEntry

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_REPO = REPO_ROOT / "tests" / "data" / "mock_repos" / "python"
UTILS_FILE = MOCK_REPO / "mock_pkg" / "utils.py"

# LanguageEntry for basedpyright (hardcoded — this is a smoke script, not a
# config consumer).
PY_ENTRY = LanguageEntry(
    name="python",
    suffixes=(".py", ".pyi"),
    server="basedpyright-langserver",
    server_args=("--stdio",),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kind_name(kind: int) -> str:
    """Human-readable name for an LSP SymbolKind integer."""
    return SYMBOL_KIND_NAMES.get(kind, f"Kind({kind})")


def _print_symbols(symbols: object, *, indent: int = 0) -> None:
    """Recursively print DocumentSymbol tree with indentation."""
    for sym in symbols:  # type: ignore[union-attr]
        name = getattr(sym, "name", "?")
        kind = getattr(sym, "kind", 0)
        prefix = "  " * indent
        print(f"[symbols] {prefix}{name} [{_kind_name(kind)}]")
        children = getattr(sym, "children", None) or []
        if children:
            _print_symbols(children, indent=indent + 1)


def _print_batch(batch: WatchBatch) -> None:
    """Print a WatchBatch summary and per-event details."""
    print(
        f"[watcher] batch: ts={batch.ts:%H:%M:%S.%f}, "
        f"raw={batch.raw}, filtered={batch.filtered}"
    )
    for ev in batch.events:
        change_name = ev.change.name  # "added", "modified", "deleted"
        print(f"[watcher]   {change_name:8s}  {ev.rel_path}")


# ---------------------------------------------------------------------------
# Phase 1: LSP init + document symbols
# ---------------------------------------------------------------------------

async def phase1_symbols(client: LspClient) -> bool:
    """Open utils.py, request symbols, print them. Returns True on success."""
    print()
    print("=" * 60)
    print("Phase 1: Document symbols for utils.py")
    print("=" * 60)

    symbols = await client.request_document_symbol_list(UTILS_FILE)

    if symbols is None:
        print("[symbols] ERROR: server returned None")
        return False

    print(f"[symbols] {len(symbols)} top-level symbol(s):")
    _print_symbols(symbols)
    return True


# ---------------------------------------------------------------------------
# Phase 2: File watcher — create/modify/delete temp file
# ---------------------------------------------------------------------------

async def phase2_watcher(
    client: LspClient, timeout_s: float = 10.0
) -> bool:
    """Run file watcher, mutate a temp .py file, print events.

    Also feeds each batch to client.notify_file_changes() so the LSP server
    stays in sync.
    """
    print()
    print("=" * 60)
    print("Phase 2: File watcher (create / modify / delete temp file)")
    print("=" * 60)

    tmp_file = MOCK_REPO / "mock_pkg" / "_smoke_tmp.py"
    batch_count = 0
    saw_create = False
    saw_modify = False
    saw_delete = False

    async def _watch_loop() -> None:
        """Collect batches until we've seen all three event types."""
        nonlocal batch_count, saw_create, saw_modify, saw_delete

        cfg = WatchConfig(debounce_ms=400)
        async for batch in awatch_repos([MOCK_REPO], cfg):
            _print_batch(batch)
            batch_count += 1

            # Feed to LSP bridge so server stays in sync.
            await client.notify_file_changes(batch)

            for ev in batch.events:
                if ev.abs_path != tmp_file:
                    continue
                if ev.change == Change.added:
                    saw_create = True
                elif ev.change == Change.modified:
                    saw_modify = True
                elif ev.change == Change.deleted:
                    saw_delete = True

            if saw_create and saw_modify and saw_delete:
                return

    # Run watcher and file mutations concurrently.
    watch_task = asyncio.create_task(_watch_loop())

    # Give the watcher a moment to start up before mutating files.
    await asyncio.sleep(0.5)

    # Create
    print("[watcher] creating temp file ...")
    tmp_file.write_text("def smoke_func():\n    return 1\n", encoding="utf-8")
    await asyncio.sleep(0.8)

    # Modify
    print("[watcher] modifying temp file ...")
    tmp_file.write_text(
        "def smoke_func():\n    return 2\n\ndef smoke_func2():\n    pass\n",
        encoding="utf-8",
    )
    await asyncio.sleep(0.8)

    # Delete
    print("[watcher] deleting temp file ...")
    tmp_file.unlink(missing_ok=True)
    await asyncio.sleep(0.8)

    # Wait for watcher to finish (with timeout so we can't hang).
    try:
        await asyncio.wait_for(asyncio.shield(watch_task), timeout=timeout_s)
    except TimeoutError:
        print(f"[watcher] WARNING: timed out after {timeout_s}s")
        watch_task.cancel()

    # Cleanup if something went wrong.
    tmp_file.unlink(missing_ok=True)

    print(f"[watcher] collected {batch_count} batch(es)")
    print(
        f"[watcher] saw create={saw_create}, modify={saw_modify}, "
        f"delete={saw_delete}"
    )

    ok = saw_create and saw_modify and saw_delete
    if not ok:
        print("[watcher] ERROR: not all event types observed")
    return ok


# ---------------------------------------------------------------------------
# Phase 3: Bridge — file change propagates to LSP
# ---------------------------------------------------------------------------

async def phase3_bridge(client: LspClient) -> bool:
    """Create a new .py file, notify LSP, open it, print its symbols.

    This proves that file changes seen by the watcher propagate through
    notify_file_changes() and the server can resolve the new file.
    """
    print()
    print("=" * 60)
    print("Phase 3: Bridge — file change propagates to LSP")
    print("=" * 60)

    new_file = MOCK_REPO / "mock_pkg" / "_smoke_bridge.py"
    new_file.unlink(missing_ok=True)

    # Create the file on disk.
    new_file.write_text(
        "def bridge_func():\n    return 42\n\ndef bridge_helper():\n    pass\n",
        encoding="utf-8",
    )

    # Build a WatchBatch manually (same shape as file_watcher would produce)
    # and send it through the LSP bridge.
    batch = WatchBatch(
        ts=datetime.now(),
        raw=1,
        filtered=1,
        events=[
            WatchEvent(
                change=Change.added,
                abs_path=new_file,
                repo_root=MOCK_REPO,
                repo_label="python",
                rel_path="mock_pkg/_smoke_bridge.py",
            )
        ],
    )

    print("[bridge] sending didChangeWatchedFiles notification ...")
    await client.notify_file_changes(batch)
    await asyncio.sleep(0.5)

    # Now ask the server for symbols — if the bridge worked, it knows the file.
    print("[bridge] requesting documentSymbol for new file ...")
    symbols = await client.request_document_symbol_list(new_file)

    if symbols is None:
        print("[bridge] ERROR: server returned None for new file")
        new_file.unlink(missing_ok=True)
        return False

    print(f"[bridge] {len(symbols)} top-level symbol(s):")
    _print_symbols(symbols)

    # Verify expected symbols are present.
    names = {getattr(s, "name", "?") for s in symbols}
    ok = True
    for expected in ("bridge_func", "bridge_helper"):
        if expected not in names:
            print(f"[bridge] ERROR: expected '{expected}' not found in {names}")
            ok = False

    if ok:
        print("[bridge] both expected symbols found — bridge working!")

    # Cleanup.
    new_file.unlink(missing_ok=True)
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Run all three phases and print a summary."""
    print("LSP E2E Smoke Test")
    print(f"  Workspace : {MOCK_REPO}")
    print(f"  Target    : {UTILS_FILE}")
    print(f"  File exists: {UTILS_FILE.exists()}")

    if not UTILS_FILE.exists():
        print(f"ERROR: {UTILS_FILE} not found", file=sys.stderr)
        sys.exit(1)

    results: dict[str, bool] = {}

    async with LspClient(lang_entry=PY_ENTRY, workspace=MOCK_REPO) as client:
        print(f"[init] server capabilities: "
              f"{type(client.server_capabilities).__name__}")

        results["symbols"] = await phase1_symbols(client)
        results["watcher"] = await phase2_watcher(client)
        results["bridge"] = await phase3_bridge(client)

    # Summary.
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    all_ok = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {name:10s} {status}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\nAll phases passed.")
    else:
        print("\nSome phases FAILED.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
