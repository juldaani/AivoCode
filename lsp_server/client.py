from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .async_process import AsyncStdioLspProcess, LspMethodNotFound
from .spec import LspServerSpec
from .types import JsonDict, JsonValue


@dataclass
class InitializeResult:
    capabilities: JsonDict


class AsyncLspClient:
    def __init__(self, process: AsyncStdioLspProcess) -> None:
        self._process = process
        self._spec = process.spec
        self._process.set_request_handler(self._handle_server_request)

    @classmethod
    async def start(cls, spec: LspServerSpec) -> "AsyncLspClient":
        process = await AsyncStdioLspProcess.start(spec)
        client = cls(process)
        await client._initialize()
        return client

    def is_running(self) -> bool:
        return self._process.is_running()

    async def request(self, method: str, params: JsonDict | None = None) -> JsonValue:
        return await self._process.request(method, params=params)

    async def notify(self, method: str, params: JsonDict | None = None) -> None:
        await self._process.notify(method, params=params)

    async def shutdown(self) -> None:
        if self._process.is_running():
            try:
                await self._process.request("shutdown")
            except Exception:
                pass
            await self._process.notify("exit")
        await self._process.close()

    async def _initialize(self) -> InitializeResult:
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
        if method == "workspace/configuration":
            return self._handle_workspace_configuration(params)
        if method == "workspace/workspaceFolders":
            return self._spec.workspace_folders
        raise LspMethodNotFound(method)

    def _handle_workspace_configuration(self, params: JsonDict | None) -> JsonValue:
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
        if section in (None, ""):
            return self._spec.settings
        if not isinstance(section, str):
            return {}
        return self._get_dotted(self._spec.settings, section)

    @staticmethod
    def _get_dotted(settings: JsonDict, section: str) -> JsonValue:
        current: JsonValue = settings
        for part in section.split("."):
            if not isinstance(current, dict):
                return {}
            if part not in current:
                return {}
            current = current[part]
        return current
