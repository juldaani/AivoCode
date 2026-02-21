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

from file_watcher import WatchConfig, awatch_repos
from watchfiles import Change

DEFAULT_CONFIG_NAME = "config.toml"

_CHANGE_LABELS: dict[Change, str] = {
    Change.added: "ADDED",
    Change.modified: "MODIFIED",
    Change.deleted: "DELETED",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LSP server from a config file.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / DEFAULT_CONFIG_NAME,
        help="Path to the AivoCode TOML config file.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help=(
            "Print file watcher events to stdout while the server is running. "
            "When enabled, the script runs until Ctrl+C."
        ),
    )
    parser.add_argument(
        "--watch-roots",
        type=Path,
        nargs="*",
        default=None,
        help=(
            "One or more directories to watch. Defaults to the configured workspace root. "
            "If multiple roots are provided, events are attributed to the deepest matching root."
        ),
    )
    parser.add_argument(
        "--watch-step-ms",
        type=int,
        default=200,
        help="Watcher step (ms) for faster yields after changes start (default: 200).",
    )
    parser.add_argument(
        "--watch-debounce-ms",
        type=int,
        default=1600,
        help="Watcher debounce (ms) to group changes (default: 1600).",
    )
    args = parser.parse_args()
    return args


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


async def _watcher_print_loop(roots: list[Path], cfg: WatchConfig) -> None:
    async for batch in awatch_repos(roots, cfg):
        ts = batch.ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"{ts}  --- batch: raw={batch.raw} filtered={batch.filtered} ---", flush=True)
        for w in batch.warnings:
            print(f"{ts}  warning: {w}", flush=True)
        # Keep output stable for easy reading.
        for ev in sorted(batch.events, key=lambda e: (e.repo_label, e.rel_path, int(e.change))):
            label = _CHANGE_LABELS.get(ev.change, str(ev.change))
            print(f"{ts}  {label:<8}  [{ev.repo_label}] {ev.rel_path}", flush=True)


async def _run_lsp_server_with_optional_watch(args: argparse.Namespace) -> None:
    config_path = args.config.resolve()
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

    watcher_task: asyncio.Task[None] | None = None
    try:
        if args.watch:
            roots = [codebase_root] if args.watch_roots is None else list(args.watch_roots)
            roots = [r.expanduser().resolve() for r in roots]

            watch_cfg = WatchConfig(
                recursive=True,
                debounce_ms=args.watch_debounce_ms,
                step_ms=args.watch_step_ms,
                defaults_filter=True,
                gitignore_filter=True,
            )
            print(
                f"Watcher enabled: roots={', '.join(str(r) for r in roots)} "
                f"(debounce_ms={watch_cfg.debounce_ms}, step_ms={watch_cfg.step_ms})",
                flush=True,
            )
            print("Press Ctrl+C to stop.", flush=True)
            watcher_task = asyncio.create_task(_watcher_print_loop(roots, watch_cfg))

            # Run until Ctrl+C; asyncio.run will cancel the main task.
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
    finally:
        if watcher_task is not None:
            watcher_task.cancel()
            await asyncio.gather(watcher_task, return_exceptions=True)

        await client.shutdown()
        print("LSP server stopped")


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run_lsp_server_with_optional_watch(args))
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
