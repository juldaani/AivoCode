from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from .basedpyright import BasedPyrightProvider
from .config import BasedPyrightConfig
from .manager import WorkspaceLspManager


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start an LSP server process.")
    parser.add_argument(
        "--server",
        default="basedpyright",
        choices=["basedpyright"],
        help="LSP server to start.",
    )
    parser.add_argument(
        "--workspace-root",
        required=True,
        help="Workspace root directory.",
    )
    parser.add_argument(
        "--config-root",
        required=True,
        help="Config root directory (absolute or workspace-relative).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level.",
    )
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    workspace_root = Path(args.workspace_root)
    config_root = Path(args.config_root)

    manager = WorkspaceLspManager()

    if args.server == "basedpyright":
        provider = BasedPyrightProvider()
        config = BasedPyrightConfig(config_root=config_root)
    else:
        raise ValueError(f"Unsupported server: {args.server}")

    logging.info("Starting %s server", provider.id)
    logging.info("Workspace root: %s", workspace_root)
    logging.info("Config root: %s", config_root)
    print(f"Starting {provider.id} server")
    print(f"Workspace root: {workspace_root}")
    print(f"Config root: {config_root}")
    client = await manager.get_or_start(
        provider=provider, workspace_root=workspace_root, config=config
    )
    logging.info("Server running: %s", client.is_running())
    print(f"Server running: {client.is_running()}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        stop_event.set()
        print("Stop signal received")

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    await stop_event.wait()
    logging.info("Shutting down %s server", provider.id)
    print(f"Shutting down {provider.id} server")
    await client.shutdown()
    logging.info("Server stopped")
    print("Server stopped")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
