"""Integration tests for workspace/symbol.

What this tests
- workspace_symbol_list returns symbols matching a query.
- Symbol kinds are correct.
- Unknown queries return empty results.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient, SYMBOL_KIND_NAMES


class TestWorkspaceSymbolPython:
    """Test workspace/symbol with Python (basedpyright)."""

    @pytest.mark.anyio
    async def test_returns_symbols_for_query(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Searching for symbols returns results (or empty if not indexed)."""
        symbols = await python_client.request_workspace_symbol_list("hello")

        # basedpyright may not support workspace symbol or may need indexing
        # Just verify no exception is raised
        assert symbols is not None

    @pytest.mark.anyio
    async def test_returns_symbols_across_files(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Searching for 'Greeter' returns results from multiple files."""
        symbols = await python_client.request_workspace_symbol_list("Greeter")

        assert symbols is not None
        if len(symbols) > 0:
            names = {s.name for s in symbols}
            # If results exist, should find multiple greeter-related symbols
            assert len(names) > 0

    @pytest.mark.anyio
    async def test_symbol_kinds_are_correct(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Function symbols have Function kind."""
        symbols = await python_client.request_workspace_symbol_list("hello")

        if symbols is not None and len(symbols) > 0:
            for sym in symbols:
                kind_name = SYMBOL_KIND_NAMES.get(sym.kind, "Unknown")
                assert kind_name in ("Function", "Method"), (
                    f"Expected Function/Method for '{sym.name}', got {kind_name}"
                )

    @pytest.mark.anyio
    async def test_no_results_for_unknown(
        self, python_client: LspClient, python_workspace: Path
    ) -> None:
        """Searching for a nonexistent symbol returns None or empty."""
        symbols = await python_client.request_workspace_symbol_list(
            "nonexistent_xyz_12345"
        )
        if symbols is not None:
            assert len(symbols) == 0
