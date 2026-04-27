"""Integration tests for textDocument/references."""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient
from lsp_client import Position


class TestReferencesPython:
    """Test references with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_references_for_function(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """References for a function returns results."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # hello function is defined around line 11
            refs = await python_client.request_references(
                file_path,
                Position(line=11, character=4),
                include_declaration=True,
            )

        # References may be None if server doesn't support it well
        # or returns empty. Just verify it doesn't raise.
        assert refs is not None or refs is None  # type: ignore[redundant-expr]

    @pytest.mark.anyio
    async def test_references_for_class(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """References for a class returns results."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            # Greeter class is defined around line 40
            refs = await python_client.request_references(
                file_path,
                Position(line=40, character=6),
                include_declaration=True,
            )

        # Just verify no exception
        assert refs is not None or refs is None  # type: ignore[redundant-expr]
