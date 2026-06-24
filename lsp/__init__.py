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
from lsp._daemon import _is_running as _daemon_is_running
from lsp._daemon import _socket_path as _daemon_socket_path
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
        - ``symbols``: list of symbol dicts (name, kind, range, children).
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


def daemon_status(workspace: Path | None = None) -> dict:
    """Check the running status of the LSP daemon for a workspace.

    Parameters
    ----------
    workspace : Path | None
        Workspace to check. If None, auto-detected from the current
        working directory (via ``detect_workspace(Path.cwd())``).

    Returns
    -------
    dict
        ``{"workspace": "...", "running": true, "language": "...", "server": "..."}``
        when the daemon is running, or ``{"workspace": "...", "running": false}``
        when it is not.
    """
    ws = workspace if workspace is not None else detect_workspace(Path.cwd())

    socket_path = _daemon_socket_path(ws)
    if not _daemon_is_running(socket_path):
        return {"workspace": str(ws), "running": False}

    try:
        result = _send_query(ws, "status", {})
    except (RuntimeError, ConnectionError, OSError):
        return {"workspace": str(ws), "running": False}

    result["workspace"] = str(ws)
    result["running"] = True
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Position-based queries — all follow the same pattern as query_document_symbols.
# ──────────────────────────────────────────────────────────────────────────────

_POSITION_METHODS = (
    "definition",
    "type_definition",
    "references",
    "hover",
    "call_hierarchy_incoming",
    "call_hierarchy_outgoing",
    "rename_edits",
)


async def _query_positional(
    file_path: Path,
    *,
    method: str,
    line: int,
    character: int,
    workspace: Path | None = None,
) -> dict:
    """Send a position-based query to the daemon and return the result dict.

    Shared implementation for definition, references, hover, call hierarchy,
    and rename_edits — all need (file, line, character).
    """
    ws = workspace if workspace is not None else detect_workspace(file_path)
    abs_path = file_path if file_path.is_absolute() else (ws / file_path).resolve()

    try:
        daemon_result = _send_query(
            ws,
            method,
            {
                "file": str(abs_path),
                "line": line,
                "character": character,
            },
        )
    except (RuntimeError, ConnectionError, OSError) as exc:
        return {
            "file": str(abs_path),
            "workspace": str(ws),
            "error": str(exc),
        }

    result: dict = {**daemon_result}
    if "workspace" not in result:
        result["workspace"] = str(ws)
    if "file" not in result:
        result["file"] = str(abs_path)
    return result


async def query_definition(
    file_path: Path,
    *,
    line: int,
    character: int,
    workspace: Path | None = None,
) -> dict:
    """Query go-to-definition for a position in *file_path*.

    Returns the location(s) where the symbol at (line, character) is defined.
    """
    return await _query_positional(
        file_path, method="definition", line=line, character=character, workspace=workspace
    )


async def query_type_definition(
    file_path: Path,
    *,
    line: int,
    character: int,
    workspace: Path | None = None,
) -> dict:
    """Query go-to-type-definition for a position in *file_path*.

    Returns the location(s) of the type declaration for the symbol.
    """
    return await _query_positional(
        file_path, method="type_definition", line=line, character=character, workspace=workspace
    )


async def query_references(
    file_path: Path,
    *,
    line: int,
    character: int,
    workspace: Path | None = None,
) -> dict:
    """Query find-references for a position in *file_path*.

    Returns all locations where the symbol at (line, character) is referenced.
    """
    return await _query_positional(
        file_path, method="references", line=line, character=character, workspace=workspace
    )


async def query_hover(
    file_path: Path,
    *,
    line: int,
    character: int,
    workspace: Path | None = None,
) -> dict:
    """Query hover information for a position in *file_path*.

    Returns the signature, type info, and docstring as markdown.
    """
    return await _query_positional(
        file_path, method="hover", line=line, character=character, workspace=workspace
    )


async def query_call_hierarchy_incoming(
    file_path: Path,
    *,
    line: int,
    character: int,
    workspace: Path | None = None,
) -> dict:
    """Query incoming call hierarchy — who calls the function at (line, character)."""
    return await _query_positional(
        file_path, method="call_hierarchy_incoming", line=line, character=character, workspace=workspace
    )


async def query_call_hierarchy_outgoing(
    file_path: Path,
    *,
    line: int,
    character: int,
    workspace: Path | None = None,
) -> dict:
    """Query outgoing call hierarchy — what the function at (line, character) calls."""
    return await _query_positional(
        file_path, method="call_hierarchy_outgoing", line=line, character=character, workspace=workspace
    )


async def query_rename_edits(
    file_path: Path,
    *,
    line: int,
    character: int,
    new_name: str,
    workspace: Path | None = None,
) -> dict:
    """Preview rename edits for a symbol without applying them.

    Returns the ``WorkspaceEdit`` that would be applied if the rename
    were committed.  Uses ``request_rename_edits`` (preview), not
    ``request_rename`` (apply).
    """
    ws = workspace if workspace is not None else detect_workspace(file_path)
    abs_path = file_path if file_path.is_absolute() else (ws / file_path).resolve()

    try:
        daemon_result = _send_query(
            ws,
            "rename_edits",
            {
                "file": str(abs_path),
                "line": line,
                "character": character,
                "new_name": new_name,
            },
        )
    except (RuntimeError, ConnectionError, OSError) as exc:
        return {
            "file": str(abs_path),
            "workspace": str(ws),
            "error": str(exc),
        }

    result: dict = {**daemon_result}
    if "workspace" not in result:
        result["workspace"] = str(ws)
    if "file" not in result:
        result["file"] = str(abs_path)
    return result


async def query_workspace_symbol(
    query: str,
    *,
    workspace: Path | None = None,
) -> dict:
    """Search for symbols across the workspace matching *query*.

    Fuzzy substring match — query ``"greet"`` matches ``Greeter``,
    ``greet``, ``greeter``, etc.
    """
    ws = workspace if workspace is not None else detect_workspace(Path.cwd())

    try:
        daemon_result = _send_query(
            ws,
            "workspace_symbol",
            {"query": query},
        )
    except (RuntimeError, ConnectionError, OSError) as exc:
        return {
            "workspace": str(ws),
            "query": query,
            "error": str(exc),
        }

    result: dict = {**daemon_result}
    if "workspace" not in result:
        result["workspace"] = str(ws)
    return result


async def query_diagnostics(
    file_path: Path,
    *,
    workspace: Path | None = None,
) -> dict:
    """Query diagnostics (errors, warnings) for *file_path*.

    Returns type errors, undefined variables, type warnings, etc.
    The file must exist (checked server-side before querying).
    """
    ws = workspace if workspace is not None else detect_workspace(file_path)
    abs_path = file_path if file_path.is_absolute() else (ws / file_path).resolve()

    try:
        daemon_result = _send_query(
            ws,
            "diagnostics",
            {"file": str(abs_path)},
        )
    except (RuntimeError, ConnectionError, OSError) as exc:
        return {
            "file": str(abs_path),
            "workspace": str(ws),
            "error": str(exc),
        }

    result: dict = {**daemon_result}
    if "workspace" not in result:
        result["workspace"] = str(ws)
    if "file" not in result:
        result["file"] = str(abs_path)
    return result


# ── Import graph queries ──────────────────────────────────────────────────────


async def _query_import(
    file_path: Path,
    *,
    method: str,
    extra_params: dict[str, str] | None = None,
    workspace: Path | None = None,
) -> dict:
    """Send an import-graph query to the daemon (no line/character needed)."""
    ws = workspace if workspace is not None else detect_workspace(file_path)
    abs_path = file_path if file_path.is_absolute() else (ws / file_path).resolve()

    params: dict[str, str] = {"file": str(abs_path)}
    if extra_params:
        params.update(extra_params)

    try:
        daemon_result = _send_query(ws, method, params)
    except (RuntimeError, ConnectionError, OSError) as exc:
        return {
            "file": str(abs_path),
            "workspace": str(ws),
            "error": str(exc),
        }

    result: dict = {**daemon_result}
    if "workspace" not in result:
        result["workspace"] = str(ws)
    return result


async def query_import_dependents(
    file_path: Path,
    *,
    depth: int = 1,
    workspace: Path | None = None,
) -> dict:
    """Query the daemon for files that (transitively) import *file_path*."""
    return await _query_import(
        file_path,
        method="import_dependents",
        extra_params={"depth": str(depth)},
        workspace=workspace,
    )


async def query_import_dependencies(
    file_path: Path,
    *,
    workspace: Path | None = None,
) -> dict:
    """Query the daemon for files that *file_path* imports."""
    return await _query_import(
        file_path,
        method="import_dependencies",
        workspace=workspace,
    )


async def query_import_affected_tests(
    file_path: Path,
    *,
    depth: int = 4,
    workspace: Path | None = None,
) -> dict:
    """Query the daemon for test files (transitively) importing *file_path*."""
    return await _query_import(
        file_path,
        method="import_affected_tests",
        extra_params={"depth": str(depth)},
        workspace=workspace,
    )


async def query_architecture(
    *,
    hotspots: int = 20,
    workspace: Path | None = None,
) -> dict:
    """Query the daemon for a high-level repo architecture report.

    Returns directory-level import relationships, entry points, and
    hotspot files — all computed from the import graph (zero LSP).
    """
    ws = workspace if workspace is not None else detect_workspace(Path.cwd())
    try:
        daemon_result = _send_query(ws, "architecture",
                                     {"hotspots": str(hotspots)})
    except (RuntimeError, ConnectionError, OSError) as exc:
        return {"workspace": str(ws), "error": str(exc)}
    result: dict = {**daemon_result}
    if "workspace" not in result:
        result["workspace"] = str(ws)
    return result


__all__ = [
    # Low-level building blocks (existing)
    "LspClient",
    "LanguageEntry",
    "load_config",
    "SYMBOL_KIND_NAMES",
    # High-level public API (existing)
    "query_document_symbols",
    "daemon_status",
    "daemon_stop",
    "result_to_output_json",
    "detect_workspace",
    # High-level public API (new — 9 methods)
    "query_definition",
    "query_type_definition",
    "query_references",
    "query_hover",
    "query_call_hierarchy_incoming",
    "query_call_hierarchy_outgoing",
    "query_rename_edits",
    "query_workspace_symbol",
    "query_diagnostics",
    # Import graph queries
    "query_import_dependents",
    "query_import_dependencies",
    "query_import_affected_tests",
    "query_architecture",
]