"""Check whether answering workspace/configuration unblocks vtsls diagnostics."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lsp import LspClient  # noqa: E402
from lsp.config import LanguageEntry  # noqa: E402
from lsp_client.capability.server_request import WithRespondConfigurationRequest  # noqa: E402
from lsp_client.capability.server_notification.log_message import WithReceiveLogMessage  # noqa: E402
from lsp_client.capability.server_notification.log_trace import WithReceiveLogTrace  # noqa: E402
from lsp_client.capability.server_notification.show_message import WithReceiveShowMessage  # noqa: E402
from lsp_client.utils.types import lsp_type  # noqa: E402


WORKSPACE = ROOT / "tests" / "data" / "mock_repos" / "typescript"
ERRORS = WORKSPACE / "mock_pkg" / "errors.ts"


class LspClientWithConfig(WithRespondConfigurationRequest, LspClient):
    """Temporary subclass that responds to vtsls workspace/configuration."""

    def create_default_config(self) -> dict[str, Any] | None:
        return {}


class VerboseLspClient(LspClient):
    """Temporary subclass to prove whether publishDiagnostics reaches LspClient."""

    async def _receive_publish_diagnostics(
        self, params: lsp_type.PublishDiagnosticsParams
    ) -> None:
        print("HOOK received", params.uri, len(params.diagnostics))
        await super()._receive_publish_diagnostics(params)


class LspClientWithLogHooks(
    WithReceiveLogMessage,
    WithReceiveLogTrace,
    WithReceiveShowMessage,
    WithRespondConfigurationRequest,
    LspClient,
):
    """Temporary subclass close to lsp-client's built-in TypeScript hooks."""

    def create_default_config(self) -> dict[str, Any] | None:
        return {}


async def run(client_cls: type[LspClient], label: str) -> None:
    entry = LanguageEntry(
        name="typescript",
        suffixes=(".ts",),
        server="vtsls",
        server_args=("--stdio",),
    )
    async with client_cls(lang_entry=entry, workspace=WORKSPACE) as client:
        async with client.open_files(ERRORS):
            await asyncio.sleep(2.0)
            diags = await client.get_diagnostics(ERRORS, timeout=3.0)
            print(label, "diagnostics", len(diags), [diag.message for diag in diags])


async def main() -> int:
    await run(LspClient, "plain")
    await run(VerboseLspClient, "verbose")
    await run(LspClientWithConfig, "with_config_response")
    await run(LspClientWithLogHooks, "with_log_and_config_hooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
