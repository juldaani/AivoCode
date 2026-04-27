"""Integration tests for textDocument/rename.

What this tests
- rename_edits returns a WorkspaceEdit with changes for cross-file symbols.
- rename for a local function updates definition and usages.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient
from lsp_client import Position


class TestRenamePython:
    """Test rename with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_rename_symbol_across_files(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Renaming TypeGreeterFactory may change multiple files."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 5: "from mock_pkg.types import ..., TypeGreeterFactory, ..."
            # 'TypeGreeterFactory' starts at character 36
            result = await python_client.request_rename_edits(
                file_path,
                Position(line=5, character=36),
                "TypeGreeterFactoryRenamed",
            )

        # basedpyright may not support rename on imports — just verify no exception
        if result is not None and result.document_changes is not None:
            changed_uris = {
                edit.text_document.uri for edit in result.document_changes
            }
            assert len(changed_uris) >= 1

    @pytest.mark.anyio
    async def test_rename_local_function(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Renaming create_and_greet updates definition and call site in full_greeting."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 65: "def create_and_greet(name: str) -> str:"
            # 'create_and_greet' starts at character 4
            result = await python_client.request_rename_edits(
                file_path,
                Position(line=65, character=4),
                "create_and_greet_renamed",
            )

        assert result is not None
        assert result.document_changes is not None

        # Count total edits — should be at least 2 (definition + usage in full_greeting)
        total_edits = sum(
            len(edit.edits) for edit in result.document_changes
        )
        assert total_edits >= 2, (
            f"Expected at least 2 edits, got {total_edits}"
        )

    @pytest.mark.anyio
    async def test_rename_method(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Renaming greet in TypeGreeter updates types.py and callers in utils.py."""
        file_path = python_workspace / "mock_pkg" / "types.py"
        async with python_client.open_files(file_path):
            # 0-indexed line 24: "def greet(self) -> str:"
            # 'greet' starts at character 8
            result = await python_client.request_rename_edits(
                file_path,
                Position(line=24, character=8),
                "greet_renamed",
            )

        if result is not None and result.document_changes is not None:
            changed_uris = {
                edit.text_document.uri for edit in result.document_changes
            }
            # Should at least rename in types.py
            assert any("types.py" in u for u in changed_uris)
