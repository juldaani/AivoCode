"""Integration tests for textDocument/rename.

What this tests
- rename_edits returns a WorkspaceEdit with at least min_edits changes (GT-driven).
- rename_edits edits contain the new name (GT-driven).
- renamed files include the must_edit_files (GT-driven).

Both LSP WorkspaceEdit formats are supported:
- Modern: document_changes (list of TextDocumentEdit)
- Legacy: changes (dict of URI → TextEdit[])
"""

from __future__ import annotations

import pytest

from lsp_client import Position
from lsp_client.utils.types import lsp_type
from tests.integration.lsp.conftest import LanguageTestData


def _extract_edits(
    result: lsp_type.WorkspaceEdit,
) -> tuple[int, list[str], set[str]]:
    """Normalize a WorkspaceEdit into (total_edits, all_new_texts, changed_uris).

    Handles both LSP WorkspaceEdit formats:
    - Modern: ``document_changes`` (list of TextDocumentEdit / CreateFile / etc.)
    - Legacy: ``changes`` (dict of URI → TextEdit[])

    Returns
    -------
    total_edits : int
        Total number of TextEdit operations across all files.
    all_new_texts : list[str]
        Every ``new_text`` value from each TextEdit (for checking rename name).
    changed_uris : set[str]
        Set of URIs for files that were edited (for checking must_edit_files).
    """
    total_edits = 0
    all_new_texts: list[str] = []
    changed_uris: set[str] = set()

    if result.document_changes is not None:
        # Modern format: list of TextDocumentEdit (plus CreateFile, etc.)
        for change in result.document_changes:
            # Only TextDocumentEdit has .edits and .text_document;
            # CreateFile, RenameFile, DeleteFile do not.
            if isinstance(change, lsp_type.TextDocumentEdit):
                uri = change.text_document.uri
                changed_uris.add(uri)
                for edit in change.edits:
                    total_edits += 1
                    # TextEdit has new_text; SnippetTextEdit also has it via parent.
                    all_new_texts.append(getattr(edit, "new_text", ""))
    elif result.changes is not None:
        # Legacy format: dict of URI → TextEdit[]
        for uri, edits in result.changes.items():
            changed_uris.add(uri)
            for edit in edits:
                total_edits += 1
                all_new_texts.append(edit.new_text)

    return total_edits, all_new_texts, changed_uris


class TestRename:
    """Test rename (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt_{gt_suffix}.json`` ground truth data.
    """

    @pytest.mark.anyio
    async def test_rename_local_function(
        self, lang: LanguageTestData
    ) -> None:
        """Renaming create_and_greet produces GT-specified number of edits."""
        gt = lang.load_gt(lang.src_file)
        gt_rename = gt["rename"]["create_def"]
        new_name = gt_rename["new_name"]
        min_edits = gt_rename["min_edits"]

        file_path = lang.file(lang.src_file)
        result = await lang.client.request_rename_edits(
            file_path,
            Position(*lang.pos("create_def")),
            new_name,
        )

        assert result is not None, (
            f"Expected rename result for {lang.name}, got None"
        )

        total_edits, all_new_texts, _ = _extract_edits(result)
        assert total_edits >= min_edits, (
            f"Expected at least {min_edits} edits for rename to '{new_name}', "
            f"got {total_edits}"
        )

        # Verify the new name appears in at least one edit.
        assert any(new_name in text for text in all_new_texts), (
            f"Expected '{new_name}' in edit texts, "
            f"got: {all_new_texts[:5]}"
        )

    @pytest.mark.anyio
    async def test_rename_method(
        self, lang: LanguageTestData
    ) -> None:
        """Renaming greet in types file produces edits in GT-specified files."""
        gt = lang.load_gt(lang.types_file)
        gt_rename = gt["rename"]["greet_def"]
        new_name = gt_rename["new_name"]
        must_edit_files = gt_rename.get("must_edit_files", [])

        types_path = lang.file(lang.types_file)
        result = await lang.client.request_rename_edits(
            types_path,
            Position(*lang.pos("greet_def")),
            new_name,
        )

        assert result is not None, (
            f"Expected rename result for {lang.name}, got None"
        )

        _, _, changed_uris = _extract_edits(result)

        # Verify each must_edit_file appears in the changed URIs.
        for expected_file in must_edit_files:
            expected_path = lang.file(expected_file)
            expected_uri = lang.client.as_uri(expected_path)
            assert expected_uri in changed_uris, (
                f"Expected {expected_file} in changed URIs, "
                f"got: {sorted(changed_uris)}"
            )