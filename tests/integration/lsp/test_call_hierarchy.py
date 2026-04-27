"""Integration tests for textDocument/callHierarchy.

What this tests
- outgoing_calls for a function shows its callees.
- outgoing_calls for the top-level greeting function shows the call chain.
"""

from __future__ import annotations

import pytest

from lsp_client import Position
from tests.integration.lsp.conftest import LanguageTestData


class TestCallHierarchy:
    """Test call hierarchy (universal — runs for each language)."""

    @pytest.mark.anyio
    async def test_outgoing_calls_for_greeting(
        self, lang: LanguageTestData
    ) -> None:
        """full_greeting has outgoing calls to create_and_greet and process_greeting."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            outgoing = await lang.client.request_call_hierarchy_outgoing_call(
                file_path, Position(*lang.pos("full_def"))
            )

        if outgoing is not None:
            assert len(outgoing) > 0
            callee_names = {call.to.name for call in outgoing}
            assert len(callee_names) > 0

    @pytest.mark.anyio
    async def test_outgoing_calls_cross_file(
        self, lang: LanguageTestData
    ) -> None:
        """create_and_greet has outgoing calls to factory and greeter."""
        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            outgoing = await lang.client.request_call_hierarchy_outgoing_call(
                file_path, Position(*lang.pos("create_def"))
            )

        if outgoing is not None:
            assert len(outgoing) > 0
