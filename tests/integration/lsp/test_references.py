"""Integration tests for textDocument/references.

What this tests
- references for a function definition returns at least min_count results
  (ground truth: utils.py/index.ts has create_def with references in the same
  file plus the definition itself).
- references for greet method returns at least min_count results
  (ground truth: types.py/types.ts has greet_def referenced from both files).
"""

from __future__ import annotations

import pytest

from lsp import SYMBOL_KIND_NAMES
from lsp_client import Position
from tests.integration.lsp.conftest import LanguageTestData


class TestReferences:
    """Test references (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt.json`` ground truth data.
    """

    @pytest.mark.anyio
    async def test_references_for_function(
        self, lang: LanguageTestData
    ) -> None:
        """References for create_and_greet definition — grounded in GT."""
        gt = lang.load_gt(lang.src_file)
        gt_refs = gt["references"]["create_def"]
        min_count = gt_refs["min_count"]

        file_path = lang.file(lang.src_file)
        refs = await lang.client.request_references(
            file_path,
            Position(*lang.pos("create_def")),
            include_declaration=True,
        )

        assert refs is not None, (
            "Expected references for create_def, got None"
        )
        assert len(refs) >= min_count, (
            f"Expected at least {min_count} references for create_def, "
            f"got {len(refs)}"
        )
        # At least one reference must point back to the source file.
        file_uri = lang.client.as_uri(file_path)
        uris = {r.uri for r in refs}
        assert file_uri in uris, (
            f"Expected at least one reference in {file_uri}, "
            f"got URIs: {sorted(uris)}"
        )

    @pytest.mark.anyio
    async def test_references_for_greet(
        self, lang: LanguageTestData
    ) -> None:
        """References for greet method — grounded in GT."""
        gt = lang.load_gt(lang.types_file)
        gt_refs = gt["references"]["greet_def"]
        min_count = gt_refs["min_count"]

        types_path = lang.file(lang.types_file)
        refs = await lang.client.request_references(
            types_path,
            Position(*lang.pos("greet_def")),
            include_declaration=True,
        )

        assert refs is not None, (
            "Expected references for greet_def, got None"
        )
        assert len(refs) >= min_count, (
            f"Expected at least {min_count} references for greet_def, "
            f"got {len(refs)}"
        )
        # greet is defined in types but called from the source file too —
        # at least one reference must point to the types file (definition).
        types_uri = lang.client.as_uri(types_path)
        uris = {r.uri for r in refs}
        assert types_uri in uris, (
            f"Expected at least one reference in {types_uri}, "
            f"got URIs: {sorted(uris)}"
        )
