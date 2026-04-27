"""Custom LSP client for aivocode.

What this module provides
- LspClient: a server-agnostic, config-driven LSP client.

How to use
- Construct with a LanguageEntry and workspace path::

    from lsp import LspClient, LanguageEntry

    entry = LanguageEntry(name="python", suffixes=[".py"], ...)
    async with LspClient(lang_entry=entry, workspace=Path.cwd()) as client:
        async with client.open_files(my_file):
            symbols = await client.request_document_symbol_list(my_file)

- Available request methods:
    - request_document_symbol_list(file_path) -> DocumentSymbol[] | None
    - request_references(file_path, position) -> Location[] | None

- File change notification (from file_watcher):
    - notify_file_changes(batch) — filters by suffix, sends didChangeWatchedFiles

See Also
- lsp.config for LanguageEntry and load_config.
- lsp.run_tst for a standalone smoke test.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from collections.abc import Sequence
from typing import Any

from attrs import define, field
from typing_extensions import override

from collections.abc import AsyncGenerator

from lsp_client import Client, LocalServer
from lsp_client.capability.request import (
    WithRequestDocumentSymbol,
    WithRequestReferences,
)
from lsp_client.server import ServerRuntimeError
from lsp_client.protocol.client import CapabilityClientProtocol
from lsp_client.protocol.lang import LanguageConfig
from lsp_client.server import ContainerServer, DefaultServers, Server
from lsp_client.settings import settings
from lsp_client.utils.types import lsp_type

from file_watcher.types import WatchBatch

from lsp.config import LanguageEntry
from lsp._translate import translate

logger = logging.getLogger(__name__)


@define
class LspClient(Client, WithRequestDocumentSymbol, WithRequestReferences):
    """Config-driven LSP client.

    Composed capabilities:
    - WithNotifyTextDocumentSynchronize (inherited from Client base)
      -- didOpen/didClose/didChange notifications and open_files() context manager.
    - WithRequestDocumentSymbol (mixed in explicitly)
      -- textDocument/documentSymbol requests.
    - WithRequestReferences (mixed in explicitly)
      -- textDocument/references requests.

    Attributes
    ----------
    lang_entry : LanguageEntry
        Configuration for this language server (program, suffixes, etc.).
    server_capabilities : ServerCapabilities | None
        Server capabilities received during initialization. Available after
        the client has been entered as async context manager.
    """

    lang_entry: LanguageEntry = field(kw_only=True)
    server_capabilities: lsp_type.ServerCapabilities | None = field(
        init=False, default=None
    )

    @classmethod
    @override
    def create_default_servers(cls) -> DefaultServers:
        """Return placeholder DefaultServers to satisfy abstract method.

        This is never actually called because _iter_candidate_servers is
        overridden below to construct servers directly from lang_entry.
        """
        raise NotImplementedError(
            "LspClient.create_default_servers is not used; "
            "_iter_candidate_servers is overridden."
        )

    @override
    async def _iter_candidate_servers(self) -> AsyncGenerator[Server, None]:
        """Iterate server candidates using LanguageEntry config.

        Overrides the default implementation to construct the local server
        from self.lang_entry instead of create_default_servers().

        Server candidates in order:
        1. User-provided server (server= constructor arg)
        2. Local server from LanguageEntry config (if available on PATH)
        3. Container server (placeholder, only if enabled in settings)
        """
        local_server = LocalServer(
            program=self.lang_entry.server,
            args=list(self.lang_entry.server_args),
        )
        container_server = ContainerServer(image=self.lang_entry.server)

        match self._server_arg:
            case "container":
                yield container_server
            case "local":
                yield local_server
            case Server() as server:
                yield server
            case _:
                pass

        with suppress(ServerRuntimeError):
            await local_server.check_availability()
            yield local_server

        if settings.enable_container:
            yield container_server
        yield local_server

    @override
    def check_server_compatibility(self, info: lsp_type.ServerInfo | None) -> None:
        """No extra compatibility checks required."""
        pass

    @classmethod
    @override
    def get_language_config(cls) -> LanguageConfig:
        """Return language configuration.

        Note: this is a classmethod but the real config is instance-specific
        (lang_entry). We return a minimal default here; in practice the
        language_id used in didOpen comes from the LanguageKind enum lookup
        based on lang_entry.name, which is handled in the open_files() flow
        by lsp-client's own logic.
        """
        return LanguageConfig(
            kind=lsp_type.LanguageKind.Python,
            suffixes=[".py"],
            project_files=["pyproject.toml"],
        )

    @override
    def create_default_config(self) -> dict[str, Any] | None:
        """Return server configuration.

        By default, returns None so the server reads its own config
        (e.g. pyproject.toml, tsconfig.json) from the workspace root.
        """
        return None

    @override
    async def _initialize(self, params: lsp_type.InitializeParams) -> None:
        """Override to store server capabilities after init."""
        result = await self.request(
            lsp_type.InitializeRequest(id="initialize", params=params),
            schema=lsp_type.InitializeResponse,
        )
        self.server_capabilities = result.capabilities
        server_info = result.server_info

        if __debug__:
            self.check_server_compatibility(server_info)
            if isinstance(self, CapabilityClientProtocol):
                self.check_server_capability(self.server_capabilities)

        await self.notify(
            lsp_type.InitializedNotification(params=lsp_type.InitializedParams())
        )

    async def notify_file_changes(self, batch: WatchBatch) -> None:
        """Translate file_watcher batch and send didChangeWatchedFiles.

        Filters events by this client's file suffixes (from LanguageEntry).
        Only sends events matching this language. No-op if no matching events.

        Parameters
        ----------
        batch : WatchBatch
            A batch of file change events from the file watcher.
        """
        file_events = translate(batch, self.lang_entry.suffixes)
        if not file_events:
            return
        await self.notify_did_change_watched_files_raw(file_events)

    async def notify_did_change_watched_files_raw(
        self, events: Sequence[lsp_type.FileEvent]
    ) -> None:
        """Send workspace/didChangeWatchedFiles with raw FileEvent objects.

        This is a lower-level alternative to notify_file_changes() for
        tests and callers that already have FileEvent objects.

        Parameters
        ----------
        events : Sequence[lsp_type.FileEvent]
            LSP FileEvent objects to send.
        """
        await self.notify(
            lsp_type.DidChangeWatchedFilesNotification(
                params=lsp_type.DidChangeWatchedFilesParams(changes=list(events))
            )
        )

    async def shutdown(self) -> None:
        """Gracefully shut down the LSP server.

        Sends shutdown request then exit notification. Idempotent — safe
        to call multiple times. This is an alternative to using the async
        context manager exit.
        """
        try:
            await self._shutdown()
        except Exception:
            pass
        try:
            await self._exit()
        except Exception:
            pass
