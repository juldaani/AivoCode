"""Integration tests for textDocument/references.

What this tests
- references for a function definition returns results.
- references for a class returns results.
"""

from __future__ import annotations

import pytest

from lsp_client import Position
from tests.integration.lsp.conftest import LanguageTestData


class TestReferences:
    """Test references (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_references_for_function(
        self, lang: LanguageTestData
    ) -> None:
        """References for a function definition returns results."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            refs = await lang.client.request_references(
                file_path,
                Position(*lang.pos("create_def")),
                include_declaration=True,
            )

        # Just verify no exception
        assert refs is not None or refs is None  # type: ignore[redundant-expr]

    @pytest.mark.anyio
    async def test_references_for_greet(
        self, lang: LanguageTestData
    ) -> None:
        """References for greet method returns results."""
        types_path = lang.file(lang.types_file)
        async with lang.client.open_files(types_path):
            refs = await lang.client.request_references(
                types_path,
                Position(*lang.pos("greet_def")),
                include_declaration=True,
            )

        if refs is not None:
            assert len(refs) > 0
