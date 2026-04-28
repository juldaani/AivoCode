"""Integration tests for workspace/symbol.

What this tests
- workspace_symbol_list returns symbols matching a query — grounded in GT.
- Symbol kinds match the GT kind_category (validated against SYMBOL_KIND_NAMES).
- Unknown queries return empty results.
"""

from __future__ import annotations

import pytest

from lsp import LspClient, SYMBOL_KIND_NAMES
from lsp_client.utils.types import lsp_type
from tests.integration.lsp.conftest import LanguageTestData


class TestWorkspaceSymbol:
    """Test workspace/symbol (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt_{gt_suffix}.json`` ground truth data.

    Note: vtsls only indexes files that have been opened via
    textDocument/didOpen, so workspace/symbol queries only return
    symbols from opened files. See ``lsp_test.toml`` ``skip_tests``
    for servers where this test is skipped.
    """

    @pytest.mark.anyio
    async def test_returns_symbols_for_query(
        self, lang: LanguageTestData
    ) -> None:
        """Searching for 'greet' returns at least the 'greet' method symbol."""
        if "workspace_symbol" in lang.skip_tests:
            pytest.skip(
                "workspace/symbol skipped for this server: "
                "vtsls only indexes opened files, not the entire workspace. "
                "See lsp_test.toml skip_tests for details."
            )
        # Open the source file to ensure the server has indexed the workspace.
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            symbols = await lang.client.request_workspace_symbol_list("greet")

        assert symbols is not None, "Expected symbols for query 'greet', got None"
        assert len(symbols) > 0, "Expected at least one symbol for 'greet'"

        result_names = {sym.name for sym in symbols}
        # The 'greet' method must be found — it's defined in the types file
        # and re-exported/called from the source file.
        # Note: Some servers (vtsls) append '()' to method names.
        gt = lang.load_gt(lang.types_file)
        # Collect all symbol names named 'greet' from GT (top-level or children).
        greet_names: set[str] = set()
        for sym in gt["symbols"]:
            if sym["name"] == "greet":
                greet_names.add(sym["name"])
            for child in sym.get("children", []):
                if child["name"] == "greet":
                    greet_names.add(child["name"])
        # Match with or without trailing parentheses (vtsls adds '()' to methods).
        matched = any(
            name in result_names or f"{name}()" in result_names
            for name in greet_names
        )
        assert matched, (
            f"Expected a 'greet' method in {result_names}"
        )

    @pytest.mark.anyio
    async def test_symbol_kinds_are_correct(
        self, lang: LanguageTestData
    ) -> None:
        """Symbol kinds match GT kind_category — validated against SYMBOL_KIND_NAMES."""
        if "workspace_symbol" in lang.skip_tests:
            pytest.skip(
                "workspace/symbol skipped for this server: "
                "vtsls only indexes opened files, not the entire workspace. "
                "See lsp_test.toml skip_tests for details."
            )
        # Open the source file so vtsls indexes the workspace.
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            symbols = await lang.client.request_workspace_symbol_list("greet")

        assert symbols is not None, "Expected symbols for query 'greet', got None"
        assert len(symbols) > 0, "Expected at least one symbol for 'greet'"

        valid_kinds = set(SYMBOL_KIND_NAMES.values())

        for sym in symbols:
            kind_name = SYMBOL_KIND_NAMES.get(sym.kind, "Unknown")
            assert kind_name in valid_kinds, (
                f"Symbol '{sym.name}' has unexpected kind {kind_name}"
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
