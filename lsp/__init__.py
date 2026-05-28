"""Custom LSP client for aivocode — library package + public API.

What this package provides

Low-level building blocks
- LspClient: a server-agnostic, config-driven LSP client with MCP-ready tools.
- LanguageEntry: dataclass for one language server configuration.
- load_config: reads lsp_config.toml and returns list[LanguageEntry].
- SYMBOL_KIND_NAMES: maps LSP SymbolKind integers to human-readable names.

High-level public API (used by CLI / MCP / REST endpoints)
- query_document_symbols: one-shot query for document symbols. Auto-detects
  workspace (via git), auto-starts the persistent LSP daemon if needed,
  serializes the result.
- daemon_stop: gracefully shut down the daemon for a workspace.
- result_to_output_json: serialize a query result dict to a JSON string.

How to use the high-level API
    from lsp import query_document_symbols, result_to_output_json

    result = await query_document_symbols(Path("src/main.py"))
    print(result_to_output_json(result))

How to use the low-level building blocks
    from lsp import LspClient, LanguageEntry, load_config

    configs = load_config(Path("lsp_config.toml"))
    for entry in configs:
        async with LspClient(lang_entry=entry, workspace=Path.cwd()) as client:
            symbols = await client.request_document_symbol_list(my_file)

See Also
- lsp.client for the full LspClient module documentation.
- lsp.config for LanguageEntry and load_config.
- lsp._symbols for SYMBOL_KIND_NAMES.
- lsp._daemon for the persistent daemon lifecycle.
- lsp._workspace for git workspace detection.
- lsp._serialize for symbol tree → JSON serialization.
- lsp_client package for the underlying library.
"""

from __future__ import annotations

from pathlib import Path

from lsp.client import LspClient
from lsp.config import LanguageEntry, load_config
from lsp._symbols import SYMBOL_KIND_NAMES

# High-level public API — these are what CLI / MCP / REST endpoints call.
from lsp._daemon import stop_daemon as daemon_stop
from lsp._daemon import send_query as _send_query
from lsp._serialize import result_to_output_json
from lsp._workspace import detect_workspace


async def query_document_symbols(
    file_path: Path,
    *,
    workspace: Path | None = None,
) -> dict:
    """Query document symbols for *file_path* via the persistent LSP daemon.

    Orchestrates the full flow:
    1. Resolves the workspace root (via git ``rev-parse --show-toplevel``,
       or uses the explicit *workspace* argument).
    2. Resolves the file to an absolute path relative to the workspace.
    3. Ensures the LSP daemon is running (auto-starts if needed).
    4. Sends a ``symbols`` query and returns the serialized result.

    Parameters
    ----------
    file_path : Path
        Path to the source file. If relative, it is resolved against
        the detected workspace root.  Absolute paths are used as-is.
    workspace : Path | None
        Explicit workspace (git repo root) override.  If None, auto-detected
        via ``detect_workspace(file_path)``.

    Returns
    -------
    dict
        A JSON‑serializable result dict with keys:
        - ``file``: absolute path to the analysed file.
        - ``workspace``: absolute path to the workspace root.
        - ``language``: language name (e.g. ``"python"``).
        - ``server``: language server binary (e.g. ``"basedpyright-langserver"``).
        - ``symbols``: list of symbol dicts (name, kind, kind_number, range, children).
        On error, the dict contains an ``error`` key instead of ``symbols``.

    Raises
    ------
    RuntimeError
        If the workspace cannot be detected (not in a git repo and no
        explicit *workspace* provided).
    """
    # ── 1. Resolve workspace ───────────────────────────────────────────
    ws = workspace if workspace is not None else detect_workspace(file_path)

    # ── 2. Resolve file path to absolute ───────────────────────────────
    if file_path.is_absolute():
        abs_path = file_path
    else:
        abs_path = (ws / file_path).resolve()

    # ── 3. Query daemon ────────────────────────────────────────────────
    try:
        daemon_result = _send_query(
            ws,
            "symbols",
            {"file": str(abs_path)},
        )
    except (RuntimeError, ConnectionError, OSError) as exc:
        return {
            "file": str(abs_path),
            "workspace": str(ws),
            "error": str(exc),
        }

    # ── 4. Enrich with top-level metadata ──────────────────────────────
    # The daemon already includes symbols, file, language, server in its
    # result. Add/overwrite workspace if the daemon didn't include it.
    result: dict = {**daemon_result}
    if "workspace" not in result:
        result["workspace"] = str(ws)
    if "file" not in result:
        result["file"] = str(abs_path)

    return result


__all__ = [
    # Low-level building blocks (existing)
    "LspClient",
    "LanguageEntry",
    "load_config",
    "SYMBOL_KIND_NAMES",
    # High-level public API (new)
    "query_document_symbols",
    "daemon_stop",
    "result_to_output_json",
    "detect_workspace",
]