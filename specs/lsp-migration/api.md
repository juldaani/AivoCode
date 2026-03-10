# LSP API Specification

## Overview

This document defines the protocols and contracts for the `lsp/` abstraction layer.

---

## Types

### `lsp/types.py`

```python
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

# Type aliases for JSON-RPC payloads
JsonValue = Any
JsonDict = dict[str, JsonValue]


class FileChangeType(IntEnum):
    """LSP file change types for workspace/didChangeWatchedFiles.
    
    Values match the LSP specification exactly.
    """
    
    created = 1
    changed = 2
    deleted = 3


@dataclass(frozen=True, slots=True)
class FileEvent:
    """A file event for workspace/didChangeWatchedFiles notification.
    
    Attributes
    ----------
    uri : str
        The file URI (e.g., "file:///path/to/file.py").
    type : FileChangeType
        The type of change that occurred.
    """
    
    uri: str
    type: FileChangeType
```

---

## Exceptions

### `lsp/exceptions.py`

```python
class LspError(Exception):
    """Base exception for LSP-related errors."""
    pass


class LspMethodNotFound(LspError):
    """Raised when a server requests a method the client doesn't support.
    
    Used when responding to server->client requests for unsupported methods.
    """
    
    def __init__(self, method: str) -> None:
        self.method = method
        super().__init__(f"Method not found: {method}")


class LspResponseError(LspError):
    """Raised when the server returns an error response.
    
    Wraps the LSP ResponseError with code, message, and optional data.
    """
    
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"LSP error {code}: {message}")
```

---

## Protocols

### `lsp/protocol.py`

#### LspClient Protocol

```python
from typing import Protocol, Sequence, runtime_checkable

from .types import FileEvent, JsonDict, JsonValue


@runtime_checkable
class LspClient(Protocol):
    """Stable interface for LSP clients.
    
    This is AivoCode's abstraction - implementations wrap different LSP libraries
    (lsp-client, multilspy, etc.).
    
    Implementations must be async-safe and handle lifecycle correctly.
    """
    
    @property
    def provider_id(self) -> str:
        """Identifier of the provider that created this client.
        
        Used for logging and debugging.
        """
        ...
    
    @property
    def instance_id(self) -> str:
        """Unique identifier for this client instance.
        
        Format is provider-specific, typically includes workspace path
        and configuration details.
        """
        ...
    
    async def request(
        self, method: str, params: JsonDict | None = None
    ) -> JsonValue:
        """Send an LSP request and await the response.
        
        Parameters
        ----------
        method : str
            The LSP method name (e.g., "textDocument/documentSymbol").
        params : JsonDict | None
            Optional parameters for the request.
        
        Returns
        -------
        JsonValue
            The response result from the server.
        
        Raises
        ------
        LspResponseError
            If the server returns an error.
        """
        ...
    
    async def notify(
        self, method: str, params: JsonDict | None = None
    ) -> None:
        """Send an LSP notification (no response expected).
        
        Parameters
        ----------
        method : str
            The LSP method name (e.g., "textDocument/didOpen").
        params : JsonDict | None
            Optional parameters for the notification.
        """
        ...
    
    async def notify_did_change_watched_files(
        self, changes: Sequence[FileEvent]
    ) -> None:
        """Send workspace/didChangeWatchedFiles notification.
        
        This is a convenience method for the most common notification
        used by AivoCode's file watcher integration.
        
        Parameters
        ----------
        changes : Sequence[FileEvent]
            List of file events to notify the server about.
        """
        ...
    
    def is_running(self) -> bool:
        """Check if the underlying LSP server is still running.
        
        Returns
        -------
        bool
            True if the server process is alive and communication is possible.
        """
        ...
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the LSP server.
        
        Sends 'shutdown' request followed by 'exit' notification,
        then terminates the server process.
        """
        ...
```

#### LspProvider Protocol

```python
from pathlib import Path
from typing import Protocol, TypeVar

from .types import JsonDict

ConfigT = TypeVar("ConfigT")


class LspProvider(Protocol[ConfigT]):
    """Factory for creating LSP clients.
    
    Each language server has its own provider that knows:
    - How to configure the server
    - How to create a client instance
    - How to extract workspace ignores from config
    - What makes instances unique (instance_id)
    
    The ConfigT type parameter is the config dataclass for this provider.
    """
    
    @property
    def id(self) -> str:
        """Unique identifier for this provider.
        
        Used in cache keys and logging.
        Examples: "basedpyright", "rust-analyzer", "java"
        """
        ...
    
    @property
    def config_class(self) -> type[ConfigT]:
        """The config dataclass for this provider.
        
        Used for type-safe configuration loading.
        """
        ...
    
    def get_instance_id(
        self, workspace_root: Path, config: ConfigT
    ) -> str:
        """Compute unique instance ID for caching.
        
        This method is called BEFORE create_client() to check if a
        client already exists in the cache.
        
        The instance_id should uniquely identify a server configuration
        within a provider. Typically includes workspace path and any
        config file path.
        
        Parameters
        ----------
        workspace_root : Path
            The workspace root directory.
        config : ConfigT
            The provider-specific configuration.
        
        Returns
        -------
        str
            Unique instance identifier.
        
        Examples
        --------
        - basedpyright: "{workspace}::{config_file}" or "{workspace}"
        - rust-analyzer: "{workspace}"
        """
        ...
    
    async def create_client(
        self,
        workspace_root: Path,
        config: ConfigT,
    ) -> "LspClient":
        """Create and start an LSP client for the given workspace.
        
        This method:
        1. Creates the backend-specific client
        2. Configures it with workspace settings
        3. Starts the server process
        4. Performs LSP initialization handshake
        5. Returns a ready-to-use client
        
        Parameters
        ----------
        workspace_root : Path
            The workspace root directory.
        config : ConfigT
            The provider-specific configuration.
        
        Returns
        -------
        LspClient
            A started and initialized LSP client.
        
        Raises
        ------
        LspError
            If server startup or initialization fails.
        """
        ...
    
    def get_workspace_ignores(
        self, workspace_root: Path, config: ConfigT
    ) -> list[str]:
        """Extract paths/patterns to ignore from the workspace config.
        
        Used by the file watcher to filter out files that the LSP server
        doesn't care about (e.g., excludes from pyrightconfig.json).
        
        Parameters
        ----------
        workspace_root : Path
            The workspace root directory.
        config : ConfigT
            The provider-specific configuration.
        
        Returns
        -------
        list[str]
            List of paths/glob patterns to ignore. Empty list if not applicable.
        """
        ...
```

---

## Manager

### `lsp/manager.py`

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .protocol import LspClient, LspProvider


@dataclass
class LspManager:
    """Cache and manage LSP client instances.
    
    Keys clients by (provider_id, instance_id) to avoid duplicate servers.
    Provides lifecycle management for all managed clients.
    
    Thread Safety
    -------------
    Not thread-safe. Use from a single async context or add external locking.
    """
    
    _clients: dict[tuple[str, str], LspClient] = field(default_factory=dict)
    
    async def get_or_start(
        self,
        provider: LspProvider[Any],
        workspace_root: Path,
        config: Any,
    ) -> LspClient:
        """Get existing client or start a new one.
        
        Reuses running clients for the same (provider_id, instance_id).
        
        Parameters
        ----------
        provider : LspProvider[Any]
            The provider to create the client if needed.
        workspace_root : Path
            The workspace root directory.
        config : Any
            The provider-specific configuration.
        
        Returns
        -------
        LspClient
            A running LSP client for the given workspace/config.
        """
        instance_id = provider.get_instance_id(workspace_root, config)
        key = (provider.id, instance_id)
        
        existing = self._clients.get(key)
        if existing is not None and existing.is_running():
            return existing
        
        client = await provider.create_client(workspace_root, config)
        self._clients[key] = client
        return client
    
    async def shutdown_all(self) -> None:
        """Shutdown all managed clients and clear the cache.
        
        Called during application teardown.
        """
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.shutdown()
```

---

## Backend: lsp-client Implementation

### `lsp/backends/lsp_client/client.py`

```python
from typing import Any, Sequence

from lsp_client.client import Client

from lsp.protocol import LspClient as LspClientProtocol
from lsp.types import FileEvent, JsonDict, JsonValue


class LspClientImpl(LspClientProtocol):
    """LspClient implementation wrapping lsp-client library.
    
    Adapts lsp-client's Client to our LspClient protocol.
    """
    
    def __init__(
        self,
        client: Client,
        provider_id: str,
        instance_id: str,
    ) -> None:
        self._client = client
        self._provider_id = provider_id
        self._instance_id = instance_id
    
    @property
    def provider_id(self) -> str:
        return self._provider_id
    
    @property
    def instance_id(self) -> str:
        return self._instance_id
    
    async def request(
        self, method: str, params: JsonDict | None = None
    ) -> JsonValue:
        return await self._client.request(method, params=params or {})
    
    async def notify(
        self, method: str, params: JsonDict | None = None
    ) -> None:
        await self._client.notify(method, params=params or {})
    
    async def notify_did_change_watched_files(
        self, changes: Sequence[FileEvent]
    ) -> None:
        """Send workspace/didChangeWatchedFiles via low-level notify.
        
        lsp-client v0.3.9 does not have a mixin for this capability,
        so we use notify() directly.
        """
        await self._client.notify(
            "workspace/didChangeWatchedFiles",
            params={
                "changes": [
                    {"uri": ev.uri, "type": int(ev.type)}
                    for ev in changes
                ]
            },
        )
    
    def is_running(self) -> bool:
        # [TBD: verify lsp-client property name]
        return self._client.is_running
    
    async def shutdown(self) -> None:
        await self._client.shutdown()
```

---

## Backend: multilspy Skeleton

### `lsp/backends/multilspy/client.py`

```python
"""multilspy backend - SKELETON ONLY.

This module provides a skeleton for future multilspy integration.
Not implemented yet - will raise NotImplementedError if used.
"""

from typing import Sequence

from lsp.protocol import LspClient as LspClientProtocol
from lsp.types import FileEvent, JsonDict, JsonValue


class MultilspyClientImpl(LspClientProtocol):
    """LspClient implementation wrapping multilspy library.
    
    SKELETON - Not implemented yet.
    """
    
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "multilspy backend is not yet implemented. "
            "Use lsp_client backend instead."
        )
    
    @property
    def provider_id(self) -> str:
        raise NotImplementedError
    
    @property
    def instance_id(self) -> str:
        raise NotImplementedError
    
    async def request(
        self, method: str, params: JsonDict | None = None
    ) -> JsonValue:
        raise NotImplementedError
    
    async def notify(
        self, method: str, params: JsonDict | None = None
    ) -> None:
        raise NotImplementedError
    
    async def notify_did_change_watched_files(
        self, changes: Sequence[FileEvent]
    ) -> None:
        raise NotImplementedError
    
    def is_running(self) -> bool:
        raise NotImplementedError
    
    async def shutdown(self) -> None:
        raise NotImplementedError
```
