"""Example usage for the lsp_server package.

What this file provides
- A runnable example that starts a basedpyright server and shuts it down.

How to read this file
- Uses the mock Python repo under tests/data/mock_repos/python by default.
- Override the paths via CLI args if needed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .basedpyright.provider import BasedPyrightProvider
from .basedpyright.config import BasedPyrightConfig
from .manager import WorkspaceLspManager

PATH_TO_REPO = Path(__file__).resolve().parents[1] / "tests" / "data" / "mock_repos" / "python"


async def _run() -> None:
    # Use the mock repo as the workspace root for this example.
    workspace_root = PATH_TO_REPO
    # Use the same folder as the config root to satisfy basedpyright validation.
    config_root = PATH_TO_REPO

    print("Starting LSP example")
    print(f"Workspace root: {workspace_root}")
    print(f"Config root: {config_root}")

    # Create a manager that caches and reuses LSP clients for this workspace.
    manager = WorkspaceLspManager()
    # Choose the basedpyright provider for Python LSP support.
    provider = BasedPyrightProvider()
    # Build the provider config with the required config root path.
    config = BasedPyrightConfig(config_root=config_root)

    # Start (or reuse) the LSP server process and get a ready client.
    client = await manager.get_or_start(
        provider=provider, workspace_root=workspace_root, config=config
    )

    print(f"Server running: {client.is_running()}")

    # The server is running in the background now. You can send LSP requests here.
    # Example: await client.request("textDocument/documentSymbol", params={...})

    # Gracefully stop the server once the example work is complete.
    await client.shutdown()
    print("Server stopped")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
