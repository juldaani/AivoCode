"""Starts an LSP server using the repo-level run_server.toml config.

This is intentionally minimal: start server, print status, then shutdown.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
from pathlib import Path
from typing import Any, Callable, Dict, Protocol, cast

from lsp_server.basedpyright.config import BasedPyrightConfig
from lsp_server.basedpyright.provider import BasedPyrightProvider
from lsp_server.manager import WorkspaceLspManager
from lsp_server.provider import LspServerProvider

DEFAULT_CONFIG_NAME = "run_server.toml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LSP server from a config file.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / DEFAULT_CONFIG_NAME,
        help="Path to the TOML config file.",
    )
    return parser.parse_args()


class _TomlModule(Protocol):
    def load(self, fp: Any) -> Dict[str, object]:
        ...


def _toml_module() -> _TomlModule:
    return cast(_TomlModule, importlib.import_module("tomllib"))


def _load_config(path: Path) -> Dict[str, object]:
    toml = _toml_module()
    with path.open("rb") as handle:
        return toml.load(handle)


def _resolve_path(value: str, base_dir: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _resolve_config_root(value: str, workspace_root: Path) -> Path:
    if value == "":
        return workspace_root
    return _resolve_path(value, workspace_root)


def _build_basedpyright_config(server_config: Dict[str, object], workspace_root: Path) -> BasedPyrightConfig:
    raw_config_root = server_config.get("config_root")
    if not isinstance(raw_config_root, str):
        raise ValueError("server.lsp.config_root must be set to a path string")
    return BasedPyrightConfig(config_root=_resolve_config_root(raw_config_root, workspace_root))


def _lsp_config_file_path(config_root: Path) -> Path:
    pyproject = config_root / "pyproject.toml"
    if pyproject.is_file():
        return pyproject
    pyrightconfig = config_root / "pyrightconfig.json"
    if pyrightconfig.is_file():
        return pyrightconfig
    return config_root


ConfigBuilder = Callable[[Dict[str, object], Path], Any]


def _provider_registry() -> dict[str, tuple[LspServerProvider[Any], ConfigBuilder]]:
    return {
        BasedPyrightProvider.id: (BasedPyrightProvider(), _build_basedpyright_config),
    }


async def _run(config_path: Path) -> None:
    config_path = config_path.resolve()
    config = _load_config(config_path)
    base_dir = config_path.parent
    server_config = config.get("server")
    if not isinstance(server_config, dict):
        raise ValueError("config must contain a [server] table")

    aivocode_config = server_config.get("aivocode")
    if not isinstance(aivocode_config, dict):
        raise ValueError("config must contain a [server.aivocode] table")

    lsp_config = server_config.get("lsp")
    if not isinstance(lsp_config, dict):
        raise ValueError("config must contain a [server.lsp] table")

    provider_id = lsp_config.get("provider")
    if not isinstance(provider_id, str):
        raise ValueError("server.lsp.provider must be set to a string")

    raw_workspace_root = aivocode_config.get("workspace_root")
    if not isinstance(raw_workspace_root, str):
        raise ValueError("server.aivocode.workspace_root must be set to a path string")
    workspace_root = _resolve_path(raw_workspace_root, base_dir)

    registry = _provider_registry()
    entry = registry.get(provider_id)
    if entry is None:
        supported = ", ".join(sorted(registry.keys()))
        raise ValueError(f"Unsupported provider: {provider_id}. Supported: {supported}")
    provider, config_builder = entry

    config_root = config_builder(lsp_config, workspace_root)

    print("Starting LSP example")
    print(f"AivoCode config file: {config_path}")
    print(f"Codebase root: {workspace_root}")
    print(f"LSP server config file: {_lsp_config_file_path(config_root.config_root)}")

    manager = WorkspaceLspManager()
    client = await manager.get_or_start(provider=provider, workspace_root=workspace_root, config=config_root)

    print(f"LSP server running: {client.is_running()}")

    await client.shutdown()
    print("LSP server stopped")


def main() -> None:
    """Entry point for the minimal LSP server runner."""
    args = _parse_args()
    asyncio.run(_run(args.config))


if __name__ == "__main__":
    main()
