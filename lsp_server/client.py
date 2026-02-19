from __future__ import annotations

"""Client wrapper that performs LSP initialization and request routing.

What this file provides
- A high-level client API that handles initialize/initialized and settings.

Why this exists
- Separates protocol bootstrapping from the low-level stdio transport.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from .async_process import AsyncStdioLspProcess, LspMethodNotFound, LspResponseError
from .spec import LspServerSpec
from .types import JsonDict, JsonValue


@dataclass
class InitializeResult:
    """Snapshot of server capabilities returned by initialize."""

    capabilities: JsonDict


class AsyncLspClient:
    """High-level LSP client over an AsyncStdioLspProcess."""

    def __init__(self, process: AsyncStdioLspProcess) -> None:
        """Bind to a running stdio LSP process."""
        self._process = process
        self._spec = process.spec
        self._process.set_request_handler(self._handle_server_request)

    @classmethod
    async def start(cls, spec: LspServerSpec) -> "AsyncLspClient":
        """Start the process, run LSP initialize, and return a ready client."""
        process = await AsyncStdioLspProcess.start(spec)
        client = cls(process)
        await client._initialize()
        return client

    def is_running(self) -> bool:
        """Return True if the underlying process has not exited."""
        return self._process.is_running()

    async def request(self, method: str, params: JsonDict | None = None) -> JsonValue:
        """Send a request and await the JSON-RPC result."""
        return await self._process.request(method, params=params)

    async def notify(self, method: str, params: JsonDict | None = None) -> None:
        """Send a notification without expecting a response."""
        await self._process.notify(method, params=params)

    async def shutdown(self) -> None:
        """Gracefully shutdown the server and terminate the subprocess."""
        if self._process.is_running():
            try:
                await self._process.request("shutdown")
            except (LspResponseError, RuntimeError):
                # If shutdown fails (server already gone), still send exit.
                pass
            await self._process.notify("exit")
        await self._process.close()

    async def _initialize(self) -> InitializeResult:
        """Run LSP initialize/initialized and apply workspace settings."""
        params: JsonDict = {
            "processId": None,
            "rootUri": self._spec.root_uri or None,
            "workspaceFolders": self._spec.workspace_folders,
            "capabilities": {
                "textDocument": {
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True
                    }
                },
                "workspace": {"symbol": {}},
            },
            "initializationOptions": self._spec.initialization_options,
        }
        result = await self._process.request("initialize", params=params)
        await self._process.notify("initialized", params={})
        if self._spec.settings:
            await self._process.notify(
                "workspace/didChangeConfiguration",
                params={"settings": self._spec.settings},
            )
        return InitializeResult(capabilities=result or {})

    async def _handle_server_request(
        self, method: str, params: JsonDict | None
    ) -> JsonValue:
        """Dispatch server-initiated requests to client handlers."""
        if method == "workspace/configuration":
            return self._handle_workspace_configuration(params)
        if method == "workspace/workspaceFolders":
            return self._spec.workspace_folders
        raise LspMethodNotFound(method)

    def _handle_workspace_configuration(self, params: JsonDict | None) -> JsonValue:
        """Respond to workspace/configuration with matching settings sections."""
        items = []
        if isinstance(params, dict):
            items = params.get("items") or []

        results: list[JsonValue] = []
        for item in items:
            section = None
            if isinstance(item, dict):
                section = item.get("section")
            results.append(self._select_settings_section(section))
        return results

    def _select_settings_section(self, section: Any) -> JsonValue:
        """Return the settings block for a dotted section path."""
        if section in (None, ""):
            return self._spec.settings
        if not isinstance(section, str):
            return {}
        return self._get_dotted(self._spec.settings, section)

    @staticmethod
    def _get_dotted(settings: JsonDict, section: str) -> JsonValue:
        """Traverse nested dicts using dotted section names."""
        current: JsonValue = settings
        for part in section.split("."):
            if not isinstance(current, dict):
                return {}
            if part not in current:
                return {}
            current = current[part]
        return current
