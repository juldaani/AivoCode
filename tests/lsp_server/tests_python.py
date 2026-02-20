from __future__ import annotations

"""Python LSP integration tests using the mock repo.

What this file provides
- A minimal basedpyright documentSymbol test against the mock Python repo.
"""

import asyncio

from lsp_server.basedpyright import BasedPyrightProvider
from lsp_server.config import BasedPyrightConfig
from lsp_server.manager import WorkspaceLspManager

from .helpers import (
    assert_symbols_match,
    did_open,
    document_symbols,
    dump_debug,
    load_tests_gt,
    mock_repo_root,
    normalize_document_symbols,
)


def test_basedpyright_document_symbols(tmp_path) -> None:
    """Fetch document symbols from the mock repo and compare to GT."""
    asyncio.run(_run_document_symbols_test(tmp_path))


async def _run_document_symbols_test(tmp_path) -> None:
    mock_root = mock_repo_root("python")
    file_path = mock_root / "mock_pkg" / "utils.py"
    gt_path = mock_root / "mock_pkg" / "utils_tests_gt.json"

    manager = WorkspaceLspManager()
    provider = BasedPyrightProvider()
    config = BasedPyrightConfig(config_root=mock_root)

    client = await manager.get_or_start(
        provider=provider, workspace_root=mock_root, config=config
    )

    try:
        await did_open(client, file_path, language_id="python")
        raw = await document_symbols(client, file_path)
        got = normalize_document_symbols(raw)
        expected = load_tests_gt(gt_path)
        expected_server = expected.get("lsp_server")
        if expected_server != provider.id:
            raise AssertionError(
                f"GT lsp_server mismatch: {expected_server} != {provider.id}"
            )
        dump_debug(tmp_path, "document_symbols_raw", raw)
        dump_debug(tmp_path, "document_symbols_normalized", got)
        dump_debug(tmp_path, "document_symbols_expected", expected.get("symbols"))
        assert_symbols_match(got, expected["symbols"])
    finally:
        await client.shutdown()
