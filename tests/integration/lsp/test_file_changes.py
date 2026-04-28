"""Integration tests for workspace/didChangeWatchedFiles notification.

What this tests
- notify_did_change_watched_files_raw sends events to the server.
- Server state updates after receiving file change notifications.
- File creation, modification, and deletion are handled.

Isolation
- Uses class-scoped python_client_isolated / python_workspace_isolated so
  each test class gets a fresh server + workspace. File mutations cannot
  leak between classes or affect read-only test modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient
from lsp_client.utils.types import lsp_type


def _file_event(uri: str, change_type: lsp_type.FileChangeType) -> lsp_type.FileEvent:
    """Helper to create a FileEvent."""
    return lsp_type.FileEvent(uri=uri, type=change_type)


class TestFileChangesPython:
    """Test didChangeWatchedFiles with Python server.

    Uses isolated fixtures so each class gets its own server + workspace.
    """

    @pytest.mark.anyio
    async def test_notify_created_file_then_open(
        self,
        python_client_isolated: LspClient,
        python_workspace_isolated: Path,
    ) -> None:
        """Create a file, notify server, then open it and verify symbols."""
        new_file = python_workspace_isolated / "mock_pkg" / "new_module.py"
        new_file.write_text(
            "def new_function(x: int) -> int:\n    return x * 2\n",
            encoding="utf-8",
        )
        try:
            await python_client_isolated.notify_did_change_watched_files_raw(
                [_file_event(new_file.as_uri(), lsp_type.FileChangeType.Created)]
            )

            symbols = await python_client_isolated.request_document_symbol_list(
                new_file
            )

            assert symbols is not None
            names = {sym.name for sym in symbols}
            assert "new_function" in names
        finally:
            new_file.unlink(missing_ok=True)

    @pytest.mark.anyio
    async def test_notify_changed_file(
        self,
        python_client_isolated: LspClient,
        python_workspace_isolated: Path,
    ) -> None:
        """Modify a file, notify server, verify updated symbols.

        Restores utils.py after the test so subsequent tests see the original.
        """
        utils_file = python_workspace_isolated / "mock_pkg" / "utils.py"
        original = utils_file.read_text(encoding="utf-8")

        try:
            # Verify symbol doesn't exist yet
            symbols_before = (
                await python_client_isolated.request_document_symbol_list(
                    utils_file
                )
            )
            assert symbols_before is not None
            names_before = {sym.name for sym in symbols_before}
            assert "brand_new_func" not in names_before

            # Modify file
            utils_file.write_text(
                original + "\n\ndef brand_new_func() -> int:\n    return 42\n",
                encoding="utf-8",
            )

            await python_client_isolated.notify_did_change_watched_files_raw(
                [_file_event(
                    utils_file.as_uri(), lsp_type.FileChangeType.Changed
                )]
            )

            # Re-verify
            symbols_after = (
                await python_client_isolated.request_document_symbol_list(
                    utils_file
                )
            )
            assert symbols_after is not None
            names_after = {sym.name for sym in symbols_after}
            assert "brand_new_func" in names_after
        finally:
            # Restore original content for other tests
            utils_file.write_text(original, encoding="utf-8")
            await python_client_isolated.notify_did_change_watched_files_raw(
                [_file_event(
                    utils_file.as_uri(), lsp_type.FileChangeType.Changed
                )]
            )

    @pytest.mark.anyio
    async def test_notify_deleted_file(
        self,
        python_client_isolated: LspClient,
        python_workspace_isolated: Path,
    ) -> None:
        """Create and delete a file, notify server, verify no crash."""
        new_file = python_workspace_isolated / "mock_pkg" / "to_delete.py"
        new_file.write_text(
            "def deleted_func() -> None:\n    pass\n", encoding="utf-8"
        )

        await python_client_isolated.notify_did_change_watched_files_raw(
            [_file_event(new_file.as_uri(), lsp_type.FileChangeType.Created)]
        )

        symbols = await python_client_isolated.request_document_symbol_list(
            new_file
        )
        assert symbols is not None
        assert "deleted_func" in {sym.name for sym in symbols}

        # Delete and notify
        new_file.unlink()
        await python_client_isolated.notify_did_change_watched_files_raw(
            [_file_event(new_file.as_uri(), lsp_type.FileChangeType.Deleted)]
        )

        # Server should still work for other files
        existing = python_workspace_isolated / "mock_pkg" / "utils.py"
        symbols = await python_client_isolated.request_document_symbol_list(
            existing
        )
        assert symbols is not None
        assert len(symbols) > 0

    @pytest.mark.anyio
    async def test_notify_batch_events(
        self,
        python_client_isolated: LspClient,
        python_workspace_isolated: Path,
    ) -> None:
        """Send multiple file events in one notification."""
        file_a = python_workspace_isolated / "mock_pkg" / "batch_a.py"
        file_b = python_workspace_isolated / "mock_pkg" / "batch_b.py"
        file_a.write_text("def func_a(): pass\n", encoding="utf-8")
        file_b.write_text("def func_b(): pass\n", encoding="utf-8")

        try:
            await python_client_isolated.notify_did_change_watched_files_raw(
                [
                    _file_event(
                        file_a.as_uri(), lsp_type.FileChangeType.Created
                    ),
                    _file_event(
                        file_b.as_uri(), lsp_type.FileChangeType.Created
                    ),
                ]
            )

            symbols_a = (
                await python_client_isolated.request_document_symbol_list(
                    file_a
                )
            )
            symbols_b = (
                await python_client_isolated.request_document_symbol_list(
                    file_b
                )
            )

            assert symbols_a is not None
            assert "func_a" in {s.name for s in symbols_a}
            assert symbols_b is not None
            assert "func_b" in {s.name for s in symbols_b}
        finally:
            file_a.unlink(missing_ok=True)
            file_b.unlink(missing_ok=True)
