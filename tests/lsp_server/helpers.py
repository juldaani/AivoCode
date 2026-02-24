from __future__ import annotations

"""Helper utilities for LSP tests.

What this file provides
- Path helpers for locating mock repos and GT files.
- LSP helpers for opening files and requesting symbols.
- Normalization and comparison helpers for deterministic assertions.
- Generic, category-based symbol checks for cross-server tests.
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


def normalize_to_kind_category(
    symbols: list[JsonDict], kind_legend: dict[str, list[int]]
) -> list[JsonDict]:
    """Map numeric kind values to semantic kind categories.

    Parameters
    ----------
    symbols : list[JsonDict]
        Normalized symbols containing "name", "kind", and "children".
    kind_legend : dict[str, list[int]]
        Mapping from category name to allowed kind numbers.
    """
    kind_map = _build_kind_category_map(kind_legend)
    return _normalize_category_list(symbols, kind_map)


def strip_local_symbol_children(
    symbols: list[JsonDict], local_parent_categories: set[str] | None = None
) -> list[JsonDict]:
    """Remove children entries for symbol categories that represent locals.

    This drops function/method local variables and parameters from symbol output
    to make cross-server comparisons more stable.
    """
    if local_parent_categories is None:
        local_parent_categories = {"Function", "Method"}

    stripped: list[JsonDict] = []
    for symbol in symbols:
        category = symbol.get("kind_category")
        children = symbol.get("children") or []
        if category in local_parent_categories:
            stripped.append(
                {"name": symbol.get("name"), "kind_category": category, "children": []}
            )
            continue
        stripped.append(
            {
                "name": symbol.get("name"),
                "kind_category": category,
                "children": strip_local_symbol_children(
                    children, local_parent_categories
                ),
            }
        )
    return _sort_symbols_by_category(stripped)


def strip_local_symbol_children_by_kind(
    symbols: list[JsonDict], local_parent_kinds: set[int]
) -> list[JsonDict]:
    """Remove children entries for symbol kinds that represent locals.

    This runs before category mapping so kinds that are not in the legend
    (such as local variables) do not cause mapping failures.
    """
    stripped: list[JsonDict] = []
    for symbol in symbols:
        kind_value = symbol.get("kind")
        kind_key = _kind_sort_key(kind_value)
        children = symbol.get("children") or []
        if kind_key in local_parent_kinds:
            stripped.append(
                {"name": symbol.get("name"), "kind": kind_value, "children": []}
            )
            continue
        stripped.append(
            {
                "name": symbol.get("name"),
                "kind": kind_value,
                "children": strip_local_symbol_children_by_kind(
                    children, local_parent_kinds
                ),
            }
        )
    return _sort_symbols(stripped)


def assert_symbols_match_category(got: list[JsonDict], expected: list[JsonDict]) -> None:
    """Assert that category-based symbols match expected GT rules."""
    got_sorted = _sort_symbols_by_category(got)
    expected_sorted = _sort_symbols_by_category(expected)

    if len(got_sorted) != len(expected_sorted):
        raise AssertionError(
            f"Symbol count mismatch: {len(got_sorted)} != {len(expected_sorted)}"
        )

    for got_item, expected_item in zip(got_sorted, expected_sorted):
        _assert_symbol_entry_category(got_item, expected_item)


async def assert_document_symbols_generic(
    tmp_path: Path,
    client: Any,
    file_path: Path,
    gt_path: Path,
    *,
    language_id: str,
) -> None:
    """Compare documentSymbol output against category-based GT."""
    await did_open(client, file_path, language_id=language_id)
    raw = await document_symbols(client, file_path)
    got = normalize_document_symbols(raw)
    expected = load_tests_gt(gt_path)
    schema_version = expected.get("schema_version")
    if schema_version != 2:
        raise AssertionError(f"Unsupported schema_version: {schema_version}")
    kind_legend = expected.get("kind_legend")
    if not isinstance(kind_legend, dict):
        raise AssertionError("Expected kind_legend mapping in GT")
    local_parent_kinds = _extract_local_parent_kinds(kind_legend)
    filtered_numeric = strip_local_symbol_children_by_kind(got, local_parent_kinds)
    categorized = normalize_to_kind_category(filtered_numeric, kind_legend)
    filtered = strip_local_symbol_children(categorized)

    dump_debug(tmp_path, "document_symbols_raw", raw)
    dump_debug(tmp_path, "document_symbols_normalized", got)
    dump_debug(tmp_path, "document_symbols_filtered_numeric", filtered_numeric)
    dump_debug(tmp_path, "document_symbols_categorized", categorized)
    dump_debug(tmp_path, "document_symbols_filtered", filtered)
    dump_debug(tmp_path, "document_symbols_expected", expected.get("symbols"))

    assert_symbols_match_category(filtered, expected["symbols"])


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


def _build_kind_category_map(kind_legend: dict[str, list[int]]) -> dict[int, str]:
    """Build a reverse lookup from kind number to category label."""
    kind_map: dict[int, str] = {}
    for category, kinds in kind_legend.items():
        if not isinstance(kinds, list):
            continue
        for kind in kinds:
            if isinstance(kind, int):
                kind_map[kind] = category
    return kind_map


def _extract_local_parent_kinds(kind_legend: dict[str, list[int]]) -> set[int]:
    """Return the kind numbers for function/method categories."""
    local_parent_kinds: set[int] = set()
    for category in ("Function", "Method"):
        kinds = kind_legend.get(category)
        if not isinstance(kinds, list):
            continue
        for kind in kinds:
            if isinstance(kind, int):
                local_parent_kinds.add(kind)
    return local_parent_kinds


def _normalize_category_list(
    items: list[JsonDict], kind_map: dict[int, str]
) -> list[JsonDict]:
    """Normalize symbol list to name/kind_category/children only."""
    normalized = [_normalize_category_symbol(item, kind_map) for item in items]
    return _sort_symbols_by_category(normalized)


def _normalize_category_symbol(item: JsonDict, kind_map: dict[int, str]) -> JsonDict:
    """Normalize a single symbol entry to kind_category."""
    kind_value = item.get("kind")
    kind_key = _kind_sort_key(kind_value)
    category = kind_map.get(kind_key)
    if category is None:
        raise AssertionError(f"Unknown symbol kind: {kind_value}")
    children = item.get("children") or []
    return {
        "name": item.get("name"),
        "kind_category": category,
        "children": _normalize_category_list(children, kind_map) if children else [],
    }


def _sort_symbols_by_category(symbols: list[JsonDict]) -> list[JsonDict]:
    """Sort symbols deterministically by category then name."""
    return sorted(
        symbols,
        key=lambda s: ((s.get("kind_category") or ""), s.get("name")),
    )


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


def _assert_symbol_entry_category(got: JsonDict, expected: JsonDict) -> None:
    """Compare a single symbol entry by kind_category."""
    if got.get("name") != expected.get("name"):
        raise AssertionError(
            f"Symbol name mismatch: {got.get('name')} != {expected.get('name')}"
        )

    got_category = got.get("kind_category")
    expected_category = expected.get("kind_category")
    if got_category != expected_category:
        raise AssertionError(
            f"Symbol category mismatch for {got.get('name')}: {got_category} != "
            f"{expected_category}"
        )

    got_children = got.get("children") or []
    expected_children = expected.get("children") or []
    assert_symbols_match_category(got_children, expected_children)


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


def copy_mock_repo(
    tmp_path: Path, language: str, src_path: Path | None = None
) -> Path:
    """Copy mock repo to tmp_path for isolated testing.

    Parameters
    ----------
    tmp_path : Path
        pytest tmp_path fixture value.
    language : str
        Language identifier (used as destination folder name).
    src_path : Path | None
        Source path to copy from. If None, uses default mock_repo_root(language).

    Returns
    -------
    Path
        Path to the copied workspace root.
    """
    src = src_path if src_path is not None else mock_repo_root(language)
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
