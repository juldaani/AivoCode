"""Integration tests for textDocument/callHierarchy.

What this tests
- outgoing_calls for a function shows GT-specified callee names.
- Cross-file call hierarchy resolves correctly.
"""

from __future__ import annotations

import pytest

from lsp_client import Position
from tests.integration.lsp.conftest import LanguageTestData


class TestCallHierarchy:
    """Test call hierarchy (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt.json`` ground truth data.
    """

    @pytest.mark.anyio
    async def test_outgoing_calls_for_greeting(
        self, lang: LanguageTestData
    ) -> None:
        """full_greeting has outgoing calls to GT-specified callees."""
        gt = lang.load_gt(lang.src_file)
        must_include = gt["call_hierarchy"]["full_def"]["must_include_callees"]

        file_path = lang.file(lang.src_file)
        outgoing = await lang.client.request_call_hierarchy_outgoing_call(
            file_path, Position(*lang.pos("full_def"))
        )

        assert outgoing is not None, (
            f"Expected call hierarchy results for full_def in {lang.name}, got None"
        )
        assert len(outgoing) > 0, "Expected at least one outgoing call"

        callee_names = {call.to.name for call in outgoing}
        for expected in must_include:
            assert expected in callee_names, (
                f"Expected callee '{expected}' in outgoing calls, "
                f"got: {sorted(callee_names)}"
            )

    @pytest.mark.anyio
    async def test_outgoing_calls_cross_file(
        self, lang: LanguageTestData
    ) -> None:
        """create_and_greet has outgoing calls to GT-specified callees."""
        gt = lang.load_gt(lang.src_file)
        must_include = gt["call_hierarchy"]["create_def"]["must_include_callees"]

        file_path = lang.file(lang.src_file)
        outgoing = await lang.client.request_call_hierarchy_outgoing_call(
            file_path, Position(*lang.pos("create_def"))
        )

        assert outgoing is not None, (
            f"Expected call hierarchy results for create_def in {lang.name}, got None"
        )
        assert len(outgoing) > 0, "Expected at least one outgoing call"

        callee_names = {call.to.name for call in outgoing}
        for expected in must_include:
            assert expected in callee_names, (
                f"Expected callee '{expected}' in outgoing calls, "
                f"got: {sorted(callee_names)}"
            )
