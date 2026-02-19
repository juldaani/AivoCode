from __future__ import annotations

"""Manage long-lived LSP clients for a workspace.

What this file provides
- A cache of running clients so callers reuse existing processes.

Why this exists
- Avoids spawning duplicate language servers for the same workspace/server pair.

Good to know
- Keys are server id + instance id.
- Use shutdown_all() during application teardown.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import AsyncLspClient
from .provider import LspServerProvider
from .spec import LspServerSpec


@dataclass
class WorkspaceLspManager:
    """Cache and reuse LSP clients keyed by server/instance."""

    _clients: dict[tuple[str, str], AsyncLspClient] = field(default_factory=dict)

    async def get_or_start(
        self,
        provider: LspServerProvider[Any],
        workspace_root: Path,
        config: Any,
    ) -> AsyncLspClient:
        """Return a running client for this workspace and provider."""
        spec = provider.spec(workspace_root=workspace_root, config=config)
        key = (spec.server_id, spec.instance_id)
        existing = self._clients.get(key)
        if existing is not None and existing.is_running():
            return existing

        client = await AsyncLspClient.start(spec)
        self._clients[key] = client
        return client

    async def shutdown_all(self) -> None:
        """Shutdown all managed clients and clear the cache."""
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.shutdown()
