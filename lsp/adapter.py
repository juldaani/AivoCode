"""Adapter that wraps an lsp-client Client as an LspClient.

What this file provides
- LspClientAdapter: implements the LspClient protocol by delegating to an
  lsp-client library Client instance.

Why this exists
- Decouples the public LspClient interface from the lsp-client library.
- Only this module and provider modules import from lsp-client — consumers
  never see it.

How it works
- Holds the lsp-client Client's async context manager open for the lifetime
  of the adapter (start() enters it, shutdown() exits it).
- Delegates generic request/notify to the underlying Server object using
  raw JSON-RPC dicts (bypasses lsp-client's typed API for these methods).
- Delegates notify_file_changes() via lsp-client's public notify() API with
  lsprotocol types — this is the proper typed path for a known LSP method.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence, cast

from lsprotocol import types as lsp_type
from lsp_client import Client
from lsp_client.jsonrpc.id import jsonrpc_uuid
from lsp_client.jsonrpc.types import RawNotification, RawRequest

from .file_events import FileEvent

log = logging.getLogger(__name__)


class LspClientAdapter:
    """Implements LspClient by wrapping an lsp-client Client instance.

    Not part of the public interface — only providers reference this.
    """

    def __init__(self, client: Client) -> None:
        """Bind to an lsp-client Client (not yet started).

        Parameters
        ----------
        client : Client
            An lsp-client Client instance. Must not be already entered as
            a context manager — start() will do that.
        """
        self._client = client
        self._started = False

    async def start(self) -> None:
        """Enter the lsp-client async context manager.

        This starts the server process, sends initialize/initialized, and
        applies default configuration — all handled by lsp-client internally.
        """
        if self._started:
            log.warning("LspClientAdapter.start() called but already started")
            return
        # Enter the lsp-client context manager manually.
        # __aenter__ starts the server, sends initialize, applies config.
        await self._client.__aenter__()
        self._started = True
        log.info("LspClientAdapter started")

    async def shutdown(self) -> None:
        """Exit the lsp-client context manager (sends shutdown + exit)."""
        if not self._started:
            return
        try:
            await self._client.__aexit__(None, None, None)
        except Exception:
            log.exception("Error during LspClientAdapter shutdown")
        finally:
            self._started = False

    def is_running(self) -> bool:
        """Return True if the context manager is active."""
        return self._started

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send an arbitrary LSP request via raw JSON-RPC.

        Bypasses lsp-client's typed request API — we don't have lsprotocol
        request/response classes for every method consumers might call.
        Instead, we send a raw request through the Server object and extract
        the result from the response.
        """
        server = self._client.get_server()
        # Generate a unique id for request/response matching.
        # lsp-client's Server.request() uses request["id"] to register a
        # pending response receiver, so the id must be unique per request.
        req_id = jsonrpc_uuid()
        req_params: list[Any] | dict[str, Any] = params or {}
        raw_req: RawRequest = {
            "id": req_id,
            "method": method,
            "params": req_params,
            "jsonrpc": "2.0",
        }
        raw_resp = await server.request(raw_req)
        # RawResponsePackage is either RawResponse or RawError
        if "error" in raw_resp and raw_resp["error"] is not None:
            error = raw_resp["error"]
            raise LspClientError(
                code=error.get("code", -1) if isinstance(error, dict) else -1,
                message=str(
                    error.get("message", "Unknown error")
                    if isinstance(error, dict)
                    else error
                ),
            )
        return raw_resp.get("result")

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send an arbitrary LSP notification via raw JSON-RPC."""
        server = self._client.get_server()
        noti_params: list[Any] | dict[str, Any] = params or {}
        raw_noti: RawNotification = {
            "method": method,
            "params": noti_params,
            "jsonrpc": "2.0",
        }
        await server.notify(raw_noti)

    async def notify_file_changes(self, changes: Sequence[FileEvent]) -> None:
        """Send workspace/didChangeWatchedFiles via lsp-client's typed notify().

        Uses lsprotocol types through the library's public Client.notify()
        method — the proper typed path for a known LSP method.
        """
        lsp_changes = [
            lsp_type.FileEvent(
                uri=ev.uri,
                type=lsp_type.FileChangeType(int(ev.type)),
            )
            for ev in changes
        ]
        notification = lsp_type.DidChangeWatchedFilesNotification(
            params=lsp_type.DidChangeWatchedFilesParams(changes=lsp_changes)
        )
        await self._client.notify(notification)


class LspClientError(Exception):
    """Error returned by the LSP server for a request."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"LSP error {code}: {message}")
        self.code = code
        self.message = message
