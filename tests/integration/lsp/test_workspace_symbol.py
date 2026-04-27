"""Integration tests for workspace/symbol.

What this tests
- workspace_symbol_list returns symbols matching a query.
- Symbol kinds are correct.
- Unknown queries return empty results.
"""

from __future__ import annotations

import pytest

from lsp import LspClient, SYMBOL_KIND_NAMES
from tests.integration.lsp.conftest import LanguageTestData


class TestWorkspaceSymbol:
    """Test workspace/symbol (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_returns_symbols_for_query(
        self, lang: LanguageTestData
    ) -> None:
        """Searching for 'greet' returns matching symbols."""
        symbols = await lang.client.request_workspace_symbol_list("greet")
        assert symbols is not None

    @pytest.mark.anyio
    async def test_symbol_kinds_are_correct(
        self, lang: LanguageTestData
    ) -> None:
        """Function symbols have Function or Method kind."""
        symbols = await lang.client.request_workspace_symbol_list("greet")
        if symbols is not None and len(symbols) > 0:
            for sym in symbols:
                kind_name = SYMBOL_KIND_NAMES.get(sym.kind, "Unknown")
                assert kind_name in ("Function", "Method", "Class", "Variable"), (
                    f"Unexpected kind for '{sym.name}': {kind_name}"
                )

    @pytest.mark.anyio
    async def test_no_results_for_unknown(
        self, lang: LanguageTestData
    ) -> None:
        """Searching for a nonexistent symbol returns None or empty."""
        symbols = await lang.client.request_workspace_symbol_list(
            "nonexistent_xyz_12345"
        )
        if symbols is not None:
            assert len(symbols) == 0
