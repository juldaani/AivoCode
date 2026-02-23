from __future__ import annotations

"""Helper utilities for LSP tests.

What this file provides
- Path helpers for locating mock repos and GT files.
- LSP helpers for opening files and requesting symbols.
- Normalization and comparison helpers for deterministic assertions.
- File event helpers for didChangeWatchedFiles tests.

Why this exists
- Keeps test logic small and reusable across languages and servers.
"""

import asyncio
import json
import os
from pathlib import Path
import shutil
from typing import Any

from lsp_server.types import FileChangeType, FileEvent, JsonDict, JsonValue


def repo_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parents[2]


def mock_repo_root(language: str) -> Path:
    """Return the mock repo root for a given language name."""
    return repo_root() / "tests" / "data" / "mock_repos" / language


def file_uri(path: Path) -> str:
    """Return a file:// URI for a local path."""
    return path.resolve().as_uri()


def load_tests_gt(path: Path) -> JsonDict:
    """Load a GT JSON file from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


async def did_open(client: Any, file_path: Path, *, language_id: str) -> None:
    """Send textDocument/didOpen for a file with its full contents."""
    text = file_path.read_text(encoding="utf-8")
    await client.notify(
        "textDocument/didOpen",
        params={
            "textDocument": {
                "uri": file_uri(file_path),
                "languageId": language_id,
                "version": 1,
                "text": text,
            }
        },
    )


async def document_symbols(
    client: Any, file_path: Path, *, timeout_s: float = 10.0
) -> JsonValue:
    """Request textDocument/documentSymbol with a timeout."""
    params = {"textDocument": {"uri": file_uri(file_path)}}
    return await asyncio.wait_for(
        client.request("textDocument/documentSymbol", params=params),
        timeout=timeout_s,
    )


def normalize_document_symbols(result: JsonValue) -> list[JsonDict]:
    """Normalize LSP symbol output to name/kind/children only.

    Supports both DocumentSymbol[] (nested) and SymbolInformation[] (flat).
    """
    if not result:
        return []

    if isinstance(result, list) and result and isinstance(result[0], dict):
        first = result[0]
        if "children" in first:
            return _normalize_document_symbol_list(result)
        return _normalize_symbol_information_list(result)

    raise TypeError(f"Unexpected documentSymbol result shape: {type(result)}")


def _normalize_document_symbol_list(items: list[dict[str, Any]]) -> list[JsonDict]:
    """Normalize nested DocumentSymbol entries."""
    normalized = [_normalize_document_symbol(item) for item in items]
    return _sort_symbols(normalized)


def _normalize_document_symbol(item: dict[str, Any]) -> JsonDict:
    """Normalize a single DocumentSymbol entry."""
    children = item.get("children") or []
    return {
        "name": item.get("name"),
        "kind": item.get("kind"),
        "children": _normalize_document_symbol_list(children) if children else [],
    }


def _normalize_symbol_information_list(items: list[dict[str, Any]]) -> list[JsonDict]:
    """Normalize flat SymbolInformation entries."""
    normalized = [
        {"name": item.get("name"), "kind": item.get("kind"), "children": []}
        for item in items
    ]
    return _sort_symbols(normalized)


def _sort_symbols(symbols: list[JsonDict]) -> list[JsonDict]:
    """Sort symbols deterministically by kind then name."""
    return sorted(symbols, key=lambda s: (_kind_sort_key(s.get("kind")), s.get("name")))


def _kind_sort_key(kind: JsonValue) -> int:
    """Return a stable sort key for kind (int or list of ints)."""
    if isinstance(kind, list) and kind:
        return int(min(kind))
    if isinstance(kind, int):
        return kind
    return -1


def assert_symbols_match(got: list[JsonDict], expected: list[JsonDict]) -> None:
    """Assert that normalized symbols match expected GT rules."""
    got_sorted = _sort_symbols(got)
    expected_sorted = _sort_symbols(expected)

    if len(got_sorted) != len(expected_sorted):
        raise AssertionError(f"Symbol count mismatch: {len(got_sorted)} != {len(expected_sorted)}")

    for got_item, expected_item in zip(got_sorted, expected_sorted):
        _assert_symbol_entry(got_item, expected_item)


def _assert_symbol_entry(got: JsonDict, expected: JsonDict) -> None:
    """Compare a single symbol entry, allowing kind lists in expected."""
    if got.get("name") != expected.get("name"):
        raise AssertionError(f"Symbol name mismatch: {got.get('name')} != {expected.get('name')}")

    _assert_kind_match(got.get("kind"), expected.get("kind"), got.get("name"))

    got_children = got.get("children") or []
    expected_children = expected.get("children") or []
    assert_symbols_match(got_children, expected_children)


def _assert_kind_match(got: JsonValue, expected: JsonValue, name: str | None) -> None:
    """Assert that a symbol kind matches an int or list of ints."""
    if isinstance(expected, list):
        if got not in expected:
            raise AssertionError(
                f"Symbol kind mismatch for {name}: {got} not in {expected}"
            )
        return
    if got != expected:
        raise AssertionError(f"Symbol kind mismatch for {name}: {got} != {expected}")


def debug_enabled() -> bool:
    """Return True if debug dumps should be written."""
    return os.getenv("LSP_TEST_DEBUG") == "1"


def dump_debug(tmp_path: Path, label: str, payload: JsonValue) -> None:
    """Write debug JSON payloads to the pytest tmp_path directory."""
    if not debug_enabled():
        return
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_path = tmp_path / f"{label}.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def copy_mock_repo(tmp_path: Path, language: str) -> Path:
    """Copy mock repo to tmp_path for isolated testing.

    Returns the path to the copied workspace root.
    """
    src = mock_repo_root(language)
    dst = tmp_path / language
    shutil.copytree(src, dst)
    return dst


async def did_close(client: Any, file_path: Path) -> None:
    """Send textDocument/didClose for a file."""
    await client.notify(
        "textDocument/didClose",
        params={"textDocument": {"uri": file_uri(file_path)}},
    )


def make_file_event(path: Path, change_type: FileChangeType) -> FileEvent:
    """Create a FileEvent for a local path."""
    return FileEvent(uri=file_uri(path), type=change_type)


async def wait_for_server_ready(client: Any, timeout_s: float = 5.0) -> None:
    """Wait for the LSP server to be ready by pinging with a simple request.

    Some servers need time after initialization before accepting requests.
    This helper waits until a basic request succeeds.
    """
    import asyncio

    start = asyncio.get_event_loop().time()
    while True:
        try:
            await client.request("textDocument/documentSymbol", params={"textDocument": {"uri": "file:///nonexistent.py"}})
            return
        except Exception:
            pass
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed > timeout_s:
            raise TimeoutError(f"LSP server not ready after {timeout_s}s")
        await asyncio.sleep(0.1)
