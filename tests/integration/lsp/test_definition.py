"""Integration tests for textDocument/definition and textDocument/typeDefinition.

What this tests
- definition resolves method calls to files containing the target definition
  (grounded in GT).
- type_definition resolves typed variables to files containing the expected type
  (grounded in GT).
- Both use markers from mock source files and GT definitions/type_definitions data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp_client import Position
from tests.integration.lsp.conftest import LanguageTestData


def _extract_target_uri(location: object) -> str:
    """Extract the target URI from a Location or LocationLink.

    LSP servers may return either Location (with .uri) or LocationLink
    (with .target_uri). This helper normalizes both cases.
    """
    if hasattr(location, "target_uri"):
        return location.target_uri  # type: ignore[union-attr]
    if hasattr(location, "uri"):
        return location.uri  # type: ignore[union-attr]
    return str(location)


class TestDefinition:
    """Test definition and type_definition (universal — runs for each language).

    Assertions are grounded in ``*_tests_gt.json`` ground truth data.
    """

    @pytest.mark.anyio
    async def test_definition_for_method_call(
        self, lang: LanguageTestData
    ) -> None:
        """Go-to-definition on .greet() call — grounded in GT.

        Different language servers may resolve .greet() to either the local
        class method or the imported type's method. We assert that at least
        one resolved location's file content contains the GT-specified name.
        """
        gt = lang.load_gt(lang.src_file)
        gt_def = gt["definitions"]["greet_call"]
        target_name_part = gt_def["target_name_contains"]

        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_definition(
                file_path, Position(*lang.find_after("greet_call", "greet"))
            )

        assert result is not None, "Expected definition results, got None"
        locations = result if isinstance(result, list) else [result]
        assert len(locations) > 0, "Expected at least one definition location"

        # Verify at least one resolved location points to a file containing
        # the GT-expected target name. Language servers may resolve the call
        # to different definitions depending on type inference.
        found = False
        for loc in locations:
            uri = _extract_target_uri(loc)
            if not uri.startswith("file://"):
                continue
            loc_path = Path(uri[len("file://") :])
            try:
                content = loc_path.read_text(encoding="utf-8")
                if target_name_part in content:
                    found = True
                    break
            except (OSError, FileNotFoundError):
                continue

        assert found, (
            f"No definition resolved to a file containing '{target_name_part}'. "
            f"Resolved URIs: {sorted(_extract_target_uri(loc) for loc in locations)}"
        )

    @pytest.mark.anyio
    async def test_type_definition_for_variable(
        self, lang: LanguageTestData
    ) -> None:
        """Go-to-type-definition on greeter variable — grounded in GT."""
        gt = lang.load_gt(lang.src_file)
        gt_td = gt["type_definitions"]["greeter_var"]
        target_file = gt_td["target_file"]
        target_name_part = gt_td["target_name_contains"]

        file_path = lang.file(lang.src_file)
        async with lang.client.open_files(file_path):
            result = await lang.client.request_type_definition(
                file_path, Position(*lang.find_after("greeter_var", "greeter"))
            )

        assert result is not None, (
            f"type_definition returned None for greeter_var in {lang.name}"
        )
        locations = result if isinstance(result, list) else [result]
        assert len(locations) > 0, "Expected at least one type definition location"

        target_path = lang.file(target_file)
        target_uri = lang.client.as_uri(target_path)
        uris = {_extract_target_uri(loc) for loc in locations}

        assert target_uri in uris, (
            f"Expected type definition in {target_file}, "
            f"got URIs: {sorted(uris)}"
        )
