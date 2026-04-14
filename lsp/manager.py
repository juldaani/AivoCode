"""Manage long-lived LSP clients for a workspace.

What this file provides
- WorkspaceLspManager: cache of running clients so callers reuse existing ones.

Why this exists
- Avoids spawning duplicate language servers for the same workspace/provider pair.

Good to know
- Keys are (provider.id, workspace_root) — no dependency on LspServerSpec.
- Use shutdown_all() during application teardown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .protocol import LspClient, LspServerProvider

log = logging.getLogger(__name__)


@dataclass
class WorkspaceLspManager:
    """Cache and reuse LSP clients keyed by (provider.id, workspace_root)."""

    _clients: dict[tuple[str, str], LspClient] = field(default_factory=dict)

    async def get_or_start(
        self,
        provider: LspServerProvider[Any],
        workspace_root: Path,
        config: Any,
    ) -> LspClient:
        """Return a running client, creating one if needed.

        - Calls provider.create_client() on first access.
        - Calls client.start() to initialize the connection.
        - Reuses existing client if running.
        """
        key = (provider.id, str(workspace_root.resolve()))
        existing = self._clients.get(key)
        if existing is not None and existing.is_running():
            return existing

        log.info("Starting LSP client for %s at %s", provider.id, workspace_root)
        client = provider.create_client(workspace_root=workspace_root, config=config)
        await client.start()
        self._clients[key] = client
        return client

    async def shutdown_all(self) -> None:
        """Shut down all managed clients and clear the cache."""
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            try:
                await client.shutdown()
            except Exception:
                log.exception("Error shutting down LSP client")
