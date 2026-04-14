"""Protocols defining the public LSP client interface.

What this file provides
- LspClient: library-agnostic interface for an LSP client connection.
- LspServerProvider: factory that creates an LspClient for a specific language server.

Why this exists
- Decouples consumers (engine, future MCP server) from any specific LSP client
  library. Adding a new language/LSP combo only requires a new provider
  implementation — no plumbing changes.

How to use
- Consumers depend on LspClient (the interface), not LspClientAdapter (the impl).
- Implement LspServerProvider per language to wire up the specific client library.
"""

from pathlib import Path
from typing import Any, Protocol, Sequence, TypeVar, runtime_checkable

from .file_events import FileEvent


# ---------------------------------------------------------------------------
# LspClient — what consumers call
# ---------------------------------------------------------------------------


@runtime_checkable
class LspClient(Protocol):
    """Library-agnostic interface for an LSP client connection.

    Implementations wrap a specific LSP client library and translate to this
    unified API. The protocol is kept minimal: generic request/notify plus
    the file-change notification that the engine's file watcher depends on.
    """

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


# ---------------------------------------------------------------------------
# LspServerProvider — what implementers provide per language
# ---------------------------------------------------------------------------


ConfigT = TypeVar("ConfigT")


class LspServerProvider(Protocol[ConfigT]):
    """Factory that creates an LspClient for a specific language server.

    Each language/LSP combo gets its own provider implementation. The provider
    knows how to configure and construct the right client; the manager just
    calls create_client() and start().
    """

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
