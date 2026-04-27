from __future__ import annotations

"""Generic Python LSP documentSymbol tests for all configured providers.

What this file provides
- A category-based documentSymbol test shared across Python LSP providers.
- A config-driven test that runs for every entry in config.toml.
"""

import asyncio
from pathlib import Path

from .config import LspTestConfig
from .conftest import start_lsp_client
from .helpers import assert_document_symbols_generic


def test_document_symbols_generic(
    tmp_path: Path,
    lsp_test_config: LspTestConfig,
    lsp_test_workspace: Path,
) -> None:
    """Fetch document symbols and compare to generic GT."""
    asyncio.run(
        _run_document_symbols_generic_test(
            tmp_path,
            lsp_test_config,
            lsp_test_workspace,
        )
    )


async def _run_document_symbols_generic_test(
    tmp_path: Path,
    lsp_test_config: LspTestConfig,
    workspace: Path,
) -> None:
    file_path = workspace / "mock_pkg" / "utils.py"
    gt_path = workspace / "mock_pkg" / "utils_tests_gt.json"

    client = await start_lsp_client(lsp_test_config, workspace)

    try:
        await assert_document_symbols_generic(
            tmp_path,
            client,
            file_path,
            gt_path,
            language_id="python",
        )
    finally:
        await client.shutdown()
