"""Start an LSP server using a small repo-level TOML config.

This script is intentionally minimal:
- Read `config.toml` (by default)
- Start the configured language server
- Print status
- Shut it down
"""

from __future__ import annotations

import argparse
import asyncio
import tomllib  # pyright: ignore[reportMissingImports]
from pathlib import Path
from typing import Any

from lsp_server.basedpyright.config import BasedPyrightConfig
from lsp_server.basedpyright.provider import BasedPyrightProvider
from lsp_server.manager import WorkspaceLspManager

DEFAULT_CONFIG_NAME = "config.toml"


def _parse_args() -> Path:
    parser = argparse.ArgumentParser(description="Run the LSP server from a config file.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / DEFAULT_CONFIG_NAME,
        help="Path to the AivoCode TOML config file.",
    )
    args = parser.parse_args()
    return args.config


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError("TOML root must be a table")
    return data


def _require_table(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid table: {key}")
    return value


def _require_str(parent: dict[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Missing or invalid string: {key}")
    return value


def _resolve_path(value: str, base_dir: Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def _resolve_lsp_config_root(codebase_root: Path, config_root_value: str) -> Path:
    # Contract:
    # - "" means: use codebase root
    # - relative path means: codebase_root/<value>
    if config_root_value == "":
        return codebase_root
    return _resolve_path(config_root_value, codebase_root)


def _detect_lsp_config_file(config_root: Path) -> Path:
    pyproject = config_root / "pyproject.toml"
    if pyproject.is_file():
        return pyproject
    pyrightconfig = config_root / "pyrightconfig.json"
    if pyrightconfig.is_file():
        return pyrightconfig
    return config_root


async def _run_lsp_server(config_path: Path) -> None:
    config_path = config_path.resolve()
    config_dir = config_path.parent
    config = _load_toml(config_path)

    server = _require_table(config, "server")
    aivocode = _require_table(server, "aivocode")
    lsp = _require_table(server, "lsp")

    codebase_root_value = _require_str(aivocode, "workspace_root")
    codebase_root = _resolve_path(codebase_root_value, config_dir)

    provider_id = _require_str(lsp, "provider")

    if provider_id == BasedPyrightProvider.id:
        provider = BasedPyrightProvider()
        config_root_value = _require_str(lsp, "config_root")
        config_root = _resolve_lsp_config_root(codebase_root, config_root_value)
        provider_config = BasedPyrightConfig(config_root=config_root)
    else:
        raise ValueError(
            f"Unsupported provider: {provider_id}. Supported: {BasedPyrightProvider.id}"
        )

    print("Starting LSP example")
    print(f"AivoCode config file: {config_path}")
    print(f"Codebase root: {codebase_root}")
    print(f"LSP server config file: {_detect_lsp_config_file(provider_config.config_root)}")

    manager = WorkspaceLspManager()
    client = await manager.get_or_start(
        provider=provider,
        workspace_root=codebase_root,
        config=provider_config,
    )

    print(f"LSP server running: {client.is_running()}")

    await client.shutdown()
    print("LSP server stopped")


def main() -> None:
    config_path = _parse_args()
    asyncio.run(_run_lsp_server(config_path))


if __name__ == "__main__":
    main()
