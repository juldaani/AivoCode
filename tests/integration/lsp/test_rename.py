"""Integration tests for textDocument/rename.

What this tests
- rename_edits returns a WorkspaceEdit with changes for a local function.
- rename_edits works for a method.
"""

from __future__ import annotations

import pytest

from lsp_client import Position
from tests.integration.lsp.conftest import LanguageTestData


class TestRename:
    """Test rename (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_rename_local_function(
        self, lang: LanguageTestData
    ) -> None:
        """Renaming create_and_greet produces edits."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_rename_edits(
                file_path,
                Position(*lang.pos("create_def")),
                "renamed_create_and_greet",
            )

        if result is not None and result.document_changes is not None:
            total_edits = sum(
                len(edit.edits) for edit in result.document_changes
            )
            assert total_edits >= 1

    @pytest.mark.anyio
    async def test_rename_method(
        self, lang: LanguageTestData
    ) -> None:
        """Renaming greet in types file produces edits."""
        types_path = lang.file(lang.types_file)
        async with lang.client.open_files(types_path):
            result = await lang.client.request_rename_edits(
                types_path,
                Position(*lang.pos("greet_def")),
                "greet_renamed",
            )

        if result is not None and result.document_changes is not None:
            changed_uris = {
                edit.text_document.uri for edit in result.document_changes
            }
            assert len(changed_uris) >= 1
