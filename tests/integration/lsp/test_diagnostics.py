"""Integration tests for diagnostics (textDocument/publishDiagnostics).

What this tests
- get_diagnostics returns errors for broken code — grounded in GT.
- Error count meets GT-specified minimum and messages match patterns.
- Clean files have no error diagnostics.

Note: servers send diagnostics when a file is opened (didOpen).
We open the file first, then query diagnostics.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from lsp_client.utils.types import lsp_type
from tests.integration.lsp.conftest import LanguageTestData


class TestDiagnostics:
    """Test diagnostics (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt.json`` ground truth data.
    """

    @pytest.mark.anyio
    async def test_diagnostics_for_type_error(
        self, lang: LanguageTestData
    ) -> None:
        """Opening errors file yields diagnostics — grounded in GT."""
        gt = lang.load_gt(lang.errors_file)
        min_errors = gt["diagnostics"]["min_errors"]

        errors_path = lang.file(lang.errors_file)
        async with lang.client.open_files(errors_path):
            await asyncio.sleep(0.5)
            diags = await lang.client.get_diagnostics(errors_path)

        assert len(diags) >= min_errors, (
            f"Expected at least {min_errors} diagnostics, "
            f"got {len(diags)}: {[d.message for d in diags]}"
        )

    @pytest.mark.anyio
    async def test_diagnostics_message_patterns(
        self, lang: LanguageTestData
    ) -> None:
        """Error messages contain GT-specified patterns — grounded in GT."""
        gt = lang.load_gt(lang.errors_file)
        must_include = gt["diagnostics"]["must_include_message_patterns"]

        errors_path = lang.file(lang.errors_file)
        async with lang.client.open_files(errors_path):
            await asyncio.sleep(0.5)
            diags = await lang.client.get_diagnostics(errors_path)

        diag_messages = " ".join(d.message for d in diags).lower()
        for pattern in must_include:
            assert pattern.lower() in diag_messages, (
                f"Expected pattern '{pattern}' in diagnostic messages. "
                f"Got: {[d.message for d in diags]}"
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
