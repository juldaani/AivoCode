"""Tests for workspace/didChangeWatchedFiles LSP notification.

What this file provides
- Tests verifying that file change notifications are sent correctly to LSP servers.
- Uses document symbols as the verification mechanism (server updates its internal
  state after receiving file change notifications).

How verification works
- Create/modify/delete files in an isolated workspace copy.
- Send workspace/didChangeWatchedFiles notification.
- Request textDocument/documentSymbol to verify server state updated.

How tests are configured
- Test configuration is loaded from config.toml (language, provider, mock_repo).
- Tests automatically run for ALL configs defined in config.toml.
- Adding a new LSP server only requires adding an entry to config.toml.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from lsp_server import FileChangeType

from .conftest import start_lsp_client
from .helpers import (
    did_close,
    did_open,
    document_symbols,
    make_file_event,
    normalize_document_symbols,
)
from .config import LspTestConfig


def _symbol_names(symbols: list) -> list[str]:
    """Extract symbol names from normalized symbol list."""
    return sorted(s.get("name") for s in symbols)


def test_notify_file_created(
    lsp_test_config: LspTestConfig, lsp_test_workspace: Path
) -> None:
    """Create a new file, notify server, verify symbols are recognized."""
    asyncio.run(
        _test_notify_file_created_impl(lsp_test_config, lsp_test_workspace)
    )


async def _test_notify_file_created_impl(
    lsp_test_config: LspTestConfig, workspace: Path
) -> None:
    client = await start_lsp_client(lsp_test_config, workspace)

    try:
        new_file = workspace / "mock_pkg" / "new_module.py"
        new_file.write_text(
            """
def new_function(x: int) -> int:
    return x * 2

class NewClass:
    def method(self) -> str:
        return "hello"
""",
            encoding="utf-8",
        )

        await client.notify_did_change_watched_files(
            [make_file_event(new_file, FileChangeType.created)]
        )

        await did_open(client, new_file, language_id="python")
        raw = await document_symbols(client, new_file)
        symbols = normalize_document_symbols(raw)
        names = _symbol_names(symbols)

        assert "new_function" in names, f"new_function not found in symbols: {names}"
        assert "NewClass" in names, f"NewClass not found in symbols: {names}"

    finally:
        await client.shutdown()


def test_notify_file_changed(
    lsp_test_config: LspTestConfig, lsp_test_workspace: Path
) -> None:
    """Modify an existing file, notify server, verify updated symbols."""
    asyncio.run(
        _test_notify_file_changed_impl(lsp_test_config, lsp_test_workspace)
    )


async def _test_notify_file_changed_impl(
    lsp_test_config: LspTestConfig, workspace: Path
) -> None:
    client = await start_lsp_client(lsp_test_config, workspace)
    utils_file = workspace / "mock_pkg" / "utils.py"

    try:
        await did_open(client, utils_file, language_id="python")
        raw_before = await document_symbols(client, utils_file)
        symbols_before = normalize_document_symbols(raw_before)
        names_before = _symbol_names(symbols_before)

        assert "brand_new_func" not in names_before

        await did_close(client, utils_file)

        original_content = utils_file.read_text(encoding="utf-8")
        modified_content = (
            original_content + "\n\ndef brand_new_func() -> int:\n    return 42\n"
        )
        utils_file.write_text(modified_content, encoding="utf-8")

        await client.notify_did_change_watched_files(
            [make_file_event(utils_file, FileChangeType.changed)]
        )

        await did_open(client, utils_file, language_id="python")
        raw_after = await document_symbols(client, utils_file)
        symbols_after = normalize_document_symbols(raw_after)
        names_after = _symbol_names(symbols_after)

        assert (
            "brand_new_func" in names_after
        ), f"brand_new_func not found after change: {names_after}"

        for name in names_before:
            assert name in names_after, f"Lost symbol {name} after change"

    finally:
        await client.shutdown()


def test_notify_file_deleted(
    lsp_test_config: LspTestConfig, lsp_test_workspace: Path
) -> None:
    """Create a file, notify server, then delete it and verify no errors."""
    asyncio.run(
        _test_notify_file_deleted_impl(lsp_test_config, lsp_test_workspace)
    )


async def _test_notify_file_deleted_impl(
    lsp_test_config: LspTestConfig, workspace: Path
) -> None:
    client = await start_lsp_client(lsp_test_config, workspace)

    try:
        new_file = workspace / "mock_pkg" / "to_delete.py"
        new_file.write_text("def deleted_func() -> None:\n    pass\n", encoding="utf-8")

        await client.notify_did_change_watched_files(
            [make_file_event(new_file, FileChangeType.created)]
        )

        await did_open(client, new_file, language_id="python")
        raw = await document_symbols(client, new_file)
        symbols = normalize_document_symbols(raw)
        names = _symbol_names(symbols)
        assert "deleted_func" in names

        await did_close(client, new_file)

        new_file.unlink()

        await client.notify_did_change_watched_files(
            [make_file_event(new_file, FileChangeType.deleted)]
        )

        existing_file = workspace / "mock_pkg" / "utils.py"
        await did_open(client, existing_file, language_id="python")
        raw = await document_symbols(client, existing_file)
        symbols = normalize_document_symbols(raw)
        assert len(symbols) > 0, "Server should still work after file deletion"

    finally:
        await client.shutdown()


def test_notify_multiple_files(
    lsp_test_config: LspTestConfig, lsp_test_workspace: Path
) -> None:
    """Batch notification with multiple file events (create + change)."""
    asyncio.run(
        _test_notify_multiple_files_impl(lsp_test_config, lsp_test_workspace)
    )


async def _test_notify_multiple_files_impl(
    lsp_test_config: LspTestConfig, workspace: Path
) -> None:
    client = await start_lsp_client(lsp_test_config, workspace)

    try:
        file_a = workspace / "mock_pkg" / "file_a.py"
        file_b = workspace / "mock_pkg" / "file_b.py"
        utils_file = workspace / "mock_pkg" / "utils.py"

        file_a.write_text("def func_a() -> str:\n    return 'a'\n", encoding="utf-8")
        file_b.write_text("def func_b() -> int:\n    return 1\n", encoding="utf-8")

        original_utils = utils_file.read_text(encoding="utf-8")
        utils_file.write_text(
            original_utils + "\ndef batch_added() -> None:\n    pass\n",
            encoding="utf-8",
        )

        await client.notify_did_change_watched_files(
            [
                make_file_event(file_a, FileChangeType.created),
                make_file_event(file_b, FileChangeType.created),
                make_file_event(utils_file, FileChangeType.changed),
            ]
        )

        await did_open(client, file_a, language_id="python")
        raw = await document_symbols(client, file_a)
        symbols = normalize_document_symbols(raw)
        assert "func_a" in _symbol_names(symbols)

        await did_open(client, file_b, language_id="python")
        raw = await document_symbols(client, file_b)
        symbols = normalize_document_symbols(raw)
        assert "func_b" in _symbol_names(symbols)

        await did_open(client, utils_file, language_id="python")
        raw = await document_symbols(client, utils_file)
        symbols = normalize_document_symbols(raw)
        assert "batch_added" in _symbol_names(symbols)

    finally:
        await client.shutdown()


def test_notify_file_renamed(
    lsp_test_config: LspTestConfig, lsp_test_workspace: Path
) -> None:
    """Rename a file (delete old + create new), verify server tracks new name."""
    asyncio.run(
        _test_notify_file_renamed_impl(lsp_test_config, lsp_test_workspace)
    )


async def _test_notify_file_renamed_impl(
    lsp_test_config: LspTestConfig, workspace: Path
) -> None:
    client = await start_lsp_client(lsp_test_config, workspace)

    try:
        old_file = workspace / "mock_pkg" / "old_name.py"
        old_file.write_text(
            "def renamed_func() -> str:\n    return 'renamed'\n", encoding="utf-8"
        )

        await client.notify_did_change_watched_files(
            [make_file_event(old_file, FileChangeType.created)]
        )

        await did_open(client, old_file, language_id="python")
        raw = await document_symbols(client, old_file)
        symbols = normalize_document_symbols(raw)
        assert "renamed_func" in _symbol_names(symbols)
        await did_close(client, old_file)

        new_file = workspace / "mock_pkg" / "new_name.py"
        old_file.rename(new_file)

        await client.notify_did_change_watched_files(
            [
                make_file_event(old_file, FileChangeType.deleted),
                make_file_event(new_file, FileChangeType.created),
            ]
        )

        await did_open(client, new_file, language_id="python")
        raw = await document_symbols(client, new_file)
        symbols = normalize_document_symbols(raw)
        assert "renamed_func" in _symbol_names(symbols)

    finally:
        await client.shutdown()