"""Integration tests for diagnostics (textDocument/publishDiagnostics).

What this tests
- get_diagnostics returns errors for broken code.
- Specific error types are detected (type error, undefined name).
- Clean files have no diagnostics.

Note: servers send diagnostics when a file is opened (didOpen).
We open the file first, then query diagnostics.
"""

from __future__ import annotations

import asyncio

import pytest

from lsp_client.utils.types import lsp_type
from tests.integration.lsp.conftest import LanguageTestData


class TestDiagnostics:
    """Test diagnostics (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_diagnostics_for_type_error(
        self, lang: LanguageTestData
    ) -> None:
        """Opening errors file yields diagnostics."""
        errors_path = lang.file(lang.errors_file)
        async with lang.client.open_files(errors_path):
            await asyncio.sleep(0.5)
            diags = await lang.client.get_diagnostics(errors_path)

        assert len(diags) > 0

    @pytest.mark.anyio
    async def test_diagnostics_has_multiple_errors(
        self, lang: LanguageTestData
    ) -> None:
        """Errors file has at least 3 diagnostics."""
        errors_path = lang.file(lang.errors_file)
        async with lang.client.open_files(errors_path):
            await asyncio.sleep(0.5)
            diags = await lang.client.get_diagnostics(errors_path)

        assert len(diags) >= 3, (
            f"Expected at least 3 diagnostics, got {len(diags)}: "
            f"{[d.message for d in diags]}"
        )

    @pytest.mark.anyio
    async def test_no_diagnostics_for_clean_file(
        self, lang: LanguageTestData
    ) -> None:
        """Source file has no error diagnostics (it's valid code)."""
        src_path = lang.file(lang.src_file)
        async with lang.client.open_files(src_path):
            await asyncio.sleep(0.5)
            diags = await lang.client.get_diagnostics(src_path)

        errors = [d for d in diags if d.severity == lsp_type.DiagnosticSeverity.Error]
        assert len(errors) == 0, (
            f"Expected no errors, got: {[d.message for d in errors]}"
        )
