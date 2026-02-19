from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import AsyncLspClient
from .provider import LspServerProvider
from .spec import LspServerSpec


@dataclass
class WorkspaceLspManager:
    _clients: dict[tuple[str, str], AsyncLspClient] = field(default_factory=dict)

    async def get_or_start(
        self,
        provider: LspServerProvider[Any],
        workspace_root: Path,
        config: Any,
    ) -> AsyncLspClient:
        spec = provider.spec(workspace_root=workspace_root, config=config)
        key = (spec.server_id, spec.instance_id)
        existing = self._clients.get(key)
        if existing is not None and existing.is_running():
            return existing

        client = await AsyncLspClient.start(spec)
        self._clients[key] = client
        return client

    async def shutdown_all(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.shutdown()
