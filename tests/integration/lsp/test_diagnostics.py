"""Integration tests for diagnostics (textDocument/publishDiagnostics).

What this tests
- get_diagnostics returns errors for broken code.
- Specific error types are detected (type error, undefined name).
- Clean files have no diagnostics.

Note: basedpyright sends diagnostics when a file is opened (didOpen).
We open the file first, then query diagnostics.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lsp import LspClient
from lsp_client.utils.types import lsp_type


class TestDiagnosticsPython:
    """Test diagnostics with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_diagnostics_for_type_error(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Opening errors.py yields a diagnostic for x: int = 'not an int'."""
        file_path = python_workspace / "mock_pkg" / "errors.py"
        async with python_client.open_files(file_path):
            await asyncio.sleep(0.5)  # let server process and send diagnostics
            diags = await python_client.get_diagnostics(file_path)

        assert len(diags) > 0
        # 0-indexed line 6: x: int = "not an int"
        type_errors = [d for d in diags if d.range.start.line == 6]
        assert len(type_errors) > 0, (
            f"Expected type error on line 7, got diagnostics on lines: "
            f"{[d.range.start.line + 1 for d in diags]}"
        )

    @pytest.mark.anyio
    async def test_diagnostics_for_undefined_name(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Opening errors.py yields a diagnostic for undefined_name."""
        file_path = python_workspace / "mock_pkg" / "errors.py"
        async with python_client.open_files(file_path):
            await asyncio.sleep(0.5)
            diags = await python_client.get_diagnostics(file_path)

        assert len(diags) > 0
        # 0-indexed line 8: y = undefined_name
        name_errors = [d for d in diags if d.range.start.line == 8]
        assert len(name_errors) > 0

    @pytest.mark.anyio
    async def test_diagnostics_for_return_type(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Opening errors.py yields a diagnostic for bad_func return type."""
        file_path = python_workspace / "mock_pkg" / "errors.py"
        async with python_client.open_files(file_path):
            await asyncio.sleep(0.5)
            diags = await python_client.get_diagnostics(file_path)

        assert len(diags) > 0
        # 0-indexed line 15: "return a + 1" in bad_func
        return_errors = [d for d in diags if d.range.start.line == 15]
        assert len(return_errors) > 0

    @pytest.mark.anyio
    async def test_diagnostics_count(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """errors.py has at least 3 diagnostics (type errors + name error)."""
        file_path = python_workspace / "mock_pkg" / "errors.py"
        async with python_client.open_files(file_path):
            await asyncio.sleep(0.5)
            diags = await python_client.get_diagnostics(file_path)

        assert len(diags) >= 3, (
            f"Expected at least 3 diagnostics, got {len(diags)}: "
            f"{[d.message for d in diags]}"
        )

    @pytest.mark.anyio
    async def test_no_diagnostics_for_clean_file(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """utils.py has no error diagnostics (it's valid code)."""
        file_path = python_workspace / "mock_pkg" / "utils.py"
        async with python_client.open_files(file_path):
            await asyncio.sleep(0.5)
            diags = await python_client.get_diagnostics(file_path)

        errors = [d for d in diags if d.severity == lsp_type.DiagnosticSeverity.Error]
        assert len(errors) == 0, (
            f"Expected no errors in utils.py, got: {[d.message for d in errors]}"
        )
