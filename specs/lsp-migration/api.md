# LSP Migration — API Contracts

## LspClient Protocol

```python
from typing import Any, Protocol, Sequence, runtime_checkable

@runtime_checkable
class LspClient(Protocol):
    """Library-agnostic interface for an LSP client connection."""

    async def start(self) -> None:
        """Initialize the LSP connection (send initialize, initialized, config).

        Must be called once before any request/notify calls.
        """
        ...

    async def shutdown(self) -> None:
        """Gracefully shut down the LSP server and close the connection."""
        ...

    def is_running(self) -> bool:
        """Return True if the client is connected and the server process is alive."""
        ...

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send an LSP request and await the response result.

        Parameters
        ----------
        method : str
            LSP method name (e.g. "textDocument/documentSymbol").
        params : dict | None
            Request parameters.

        Returns
        -------
        Any
            The JSON-decoded result from the server response.
        """
        ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send an LSP notification (no response expected).

        Parameters
        ----------
        method : str
            LSP method name (e.g. "workspace/didChangeConfiguration").
        params : dict | None
            Notification parameters.
        """
        ...

    async def notify_file_changes(self, changes: Sequence[FileEvent]) -> None:
        """Notify the server about file changes in the workspace.

        Parameters
        ----------
        changes : Sequence[FileEvent]
            List of file events with URI and change type.
        """
        ...
```

## LspServerProvider Protocol

```python
from pathlib import Path
from typing import Protocol, TypeVar

ConfigT = TypeVar("ConfigT")


class LspServerProvider(Protocol[ConfigT]):
    """Factory that creates an LspClient for a specific language server."""

    id: str
    """Unique identifier for this provider (e.g. "basedpyright")."""

    def create_client(self, workspace_root: Path, config: ConfigT) -> LspClient:
        """Create a client configured for the given workspace.

        The returned client is NOT started — caller must call start().

        Parameters
        ----------
        workspace_root : Path
            Absolute path to the workspace root.
        config : ConfigT
            Language-specific configuration object.

        Returns
        -------
        LspClient
            A ready-to-start LSP client instance.
        """
        ...

    def get_workspace_ignores(self, workspace_root: Path, config: ConfigT) -> list[str]:
        """Return glob/path patterns to exclude from file watching.

        Parameters
        ----------
        workspace_root : Path
            Absolute path to the workspace root.
        config : ConfigT
            Language-specific configuration object.

        Returns
        -------
        list[str]
            List of exclude patterns (paths or globs).
        """
        ...
```

## WorkspaceLspManager

```python
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
        ...

    async def shutdown_all(self) -> None:
        """Shut down all managed clients and clear the cache."""
        ...
```

## FileEvent & FileChangeType

```python
class FileChangeType(IntEnum):
    """LSP file change types. Values match the LSP specification."""
    created = 1
    changed = 2
    deleted = 3


@dataclass(frozen=True, slots=True)
class FileEvent:
    """A file event for workspace/didChangeWatchedFiles notification."""
    uri: str
    type: FileChangeType
```

## LspClientAdapter (lsp-client implementation)

```python
class LspClientAdapter:
    """Implements LspClient by wrapping an lsp-client Client instance.

    Not part of the public interface — only providers reference this.
    """

    def __init__(self, client: Client) -> None:
        """Bind to an lsp-client Client (not yet started)."""
        ...

    async def start(self) -> None:
        """Enter the lsp-client async context manager."""
        # await self._client.__aenter__()
        ...

    async def shutdown(self) -> None:
        """Exit the lsp-client context manager."""
        # await self._client.__aexit__(None, None, None)
        ...

    def is_running(self) -> bool:
        """True if the context manager is active."""
        ...

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Delegate to lsp-client's server.request() with raw JSON-RPC."""
        ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Delegate to lsp-client's server.notify() with raw JSON-RPC."""
        ...

    async def notify_file_changes(self, changes: Sequence[FileEvent]) -> None:
        """Send workspace/didChangeWatchedFiles via lsp-client notify().

        Uses lsprotocol types:
            DidChangeWatchedFilesNotification(
                params=DidChangeWatchedFilesParams(
                    changes=[FileEvent(uri=..., type=FileChangeType(...))]
                )
            )
        """
        ...
```

## BasedPyrightProvider

```python
class BasedPyrightProvider:
    """Creates LspClient instances for basedpyright."""

    id: str = "basedpyright"

    def create_client(self, workspace_root: Path, config: BasedPyrightConfig) -> LspClient:
        """Build a BasedpyrightClient + LocalServer, wrap in LspClientAdapter."""
        # from lsp_client import BasedpyrightClient, LocalServer
        # client = BasedpyrightClient(
        #     server=LocalServer(program="basedpyright-langserver", args=["--stdio"]),
        #     workspace=workspace_root,
        #     initialization_options={...},
        # )
        # return LspClientAdapter(client)
        ...

    def get_workspace_ignores(self, workspace_root: Path, config: BasedPyrightConfig) -> list[str]:
        """Parse exclude patterns from pyproject.toml or pyrightconfig.json."""
        # Migrated from lsp_server/basedpyright/provider.py — identical logic
        ...
```

## BasedPyrightConfig

```python
@dataclass(frozen=True)
class BasedPyrightConfig:
    """Configuration for basedpyright. Migrated from lsp_server."""
    config_file: Path | None = None
```

`resolve_and_validate_config_file()` also migrated from `lsp_server/basedpyright/config.py` — same logic, new home.
