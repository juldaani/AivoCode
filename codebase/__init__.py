"""Codebase exploration tools — agent-facing derived intelligence on top of LSP.

What this module provides
- High-level, single-call tools for codebase exploration designed for AI
  agents.  Compose multiple LSP primitives into one response so agents
  spend fewer round-trips understanding code.

Why this exists
- Raw LSP tools expose protocol-level data (URIs, ranges, raw kinds).
  Agents need semantic answers (what does this function do? who calls
  it? what would break if I changed it?).  This module composes the
  low-level LSP calls into high-level "understanding primitives."

How to use
    from codebase import get_repo_tree
    tree = get_repo_tree(Path("/workspaces/my-project"))
    # → {"root": [...], "workspace": "...", "query": {...}}

Public API
----------
- get_repo_tree : build a recursive ``{"dirname/": [...]}`` tree.
- read_symbol : read the full body of a symbol.
- incoming_calls / outgoing_calls : call hierarchy.
- find_references : where is this symbol used?
- file_overview : file ToC with signatures and reference counts.
- explain_symbol : full symbol report (body, callers, callees, references).
- search_symbols : workspace-wide symbol search.
- analyze_impact : change impact (incoming + outgoing + references).
- import_dependents : who (transitively) imports this file? (zero LSP)
- import_dependencies : what does this file import? (zero LSP)
- affected_test_files : which test files are affected? (zero LSP)

See Also
- lsp/  — raw LSP protocol layer (hover, definition, references, etc.)
"""

from __future__ import annotations

from pathlib import Path

from codebase._analyze import (
    _definition,
    _diagnostics,
    _explain,
    _hover,
    _impact,
    _incoming_calls,
    _maybe_compact,
    _outgoing_calls,
    _overview,
    _references,
    _search,
)
from codebase._read import _read_symbol
from codebase._resolve import ResolvedSymbol, relativize, resolve_symbol
from codebase._tree import _build_tree


# ── Query helper ───────────────────────────────────────────────────────────────


def _make_query(command: str, **kwargs: object) -> dict:
    """Build a query metadata block, omitting ``None`` values."""
    return {"command": command, **{k: v for k, v in kwargs.items() if v is not None}}


def _make_meta(
    workspace: Path | str,
    *,
    lsp: str | None = None,
    language: str | None = None,
    info: str | None = None,
) -> dict:
    """Build the ``meta`` block shared by every codebase tool.

    ``lsp`` is the language server name (``None`` for non-LSP tools like
    import-graph).  ``info`` is an optional human-readable status string
    (graph build health, errors, etc.).
    """
    meta: dict = {"root": str(workspace)}
    if lsp:
        meta["lsp"] = lsp
    if language:
        meta["language"] = language
    if info is not None:
        meta["info"] = info
    return meta


def _format_info(info: dict) -> str | None:
    """Convert graph info dict to an optional human-readable status string.

    Returns ``None`` when there is nothing noteworthy to report (no errors,
    no skipped files).  Otherwise returns a compact status string like
    ``"103 files indexed, 2 errors"``.
    """
    indexed = info.get("files_indexed", 0)
    skipped = info.get("files_skipped", 0)
    errors = info.get("errors", [])

    has_news = skipped > 0 or errors
    if not has_news:
        return None

    parts = [f"{indexed} files indexed"]
    if skipped:
        parts.append(f"{skipped} skipped")
    if errors:
        parts.append(f"{len(errors)} errors")

    return ", ".join(parts)


def get_repo_tree(
    workspace: Path | None = None,
    *,
    suffix: str | None = None,
) -> dict:
    """Build a recursive file/directory tree for the workspace.

    Returns a nested structure where each entry is either:

    - ``"filename"`` for files, or
    - ``{"dirname/": [...children]}`` for directories.

    Hidden entries (``.git``, ``__pycache__``, etc.) are excluded.

    Parameters
    ----------
    workspace : Path or None
        Absolute path to the workspace root.  Defaults to ``Path.cwd()``.
    suffix : str or None
        When set (e.g. ``".py"``), only files with that extension are
        included.  Empty directories are pruned.
    """
    ws = workspace or Path.cwd()
    return {
        "tree": _build_tree(ws, suffix=suffix),
        "query": _make_query("tree", suffix=suffix),
        "meta": _make_meta(ws),
    }


async def read_symbol(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "read-symbol",
) -> dict:
    """Read the full body text of *symbol_name* in *file_path*.

    Returns a dict with ``symbol``, ``kind``, ``body``, ``range_line_char``,
    ``file``, ``imports``, and ``query``.  The ``imports`` list contains all
    import statements in the file, including lazy imports inside function
    bodies.  Each entry has ``{line, statement, lazy}`` — ``lazy`` is
    ``True`` for imports nested inside a ``def``/``class`` body.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = _read_symbol(sym, file_path, workspace)
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    result["meta"] = _make_meta(ws_rel, lsp=sym.lsp_server, language=sym.language)
    return result


async def incoming_calls(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    max_sites: int = 50,
    workspace: Path | None = None,
    command: str = "incoming-calls",
) -> dict:
    """List incoming call hierarchy for *symbol_name*.

    Each call entry includes a ``locality`` field (``"same_file"``,
    ``"cross_file"``, or ``"external"``)."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    groups = await _incoming_calls(sym, file_path, workspace)
    compacted, _total, info_msg = _maybe_compact(groups, max_sites=max_sites)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "incoming_calls": compacted,
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    if max_sites != 50:
        result["query"]["max"] = max_sites
    result["meta"] = _make_meta(
        ws_rel, lsp=sym.lsp_server, language=sym.language, info=info_msg,
    )
    return result


async def outgoing_calls(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    max_sites: int = 50,
    workspace: Path | None = None,
    workspace_only: bool = True,
    command: str = "outgoing-calls",
) -> dict:
    """List outgoing call hierarchy for *symbol_name*.

    By default (``workspace_only=True``), external calls (stdlib,
    site-packages) are excluded.  Pass ``workspace_only=False`` to include
    them.  Each call entry has a ``locality`` field: ``"same_file"``,
    ``"cross_file"``, or ``"external"``.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    groups = await _outgoing_calls(
        sym, file_path, workspace, workspace_only=workspace_only,
    )
    compacted, _total, info_msg = _maybe_compact(groups, max_sites=max_sites)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "outgoing_calls": compacted,
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    if max_sites != 50:
        result["query"]["max"] = max_sites
    result["meta"] = _make_meta(
        ws_rel, lsp=sym.lsp_server, language=sym.language, info=info_msg,
    )
    return result


async def find_references(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    max_sites: int = 50,
    workspace: Path | None = None,
    command: str = "references",
) -> dict:
    """List all reference sites for *symbol_name* (includes definition).

    Each reference entry includes a ``locality`` field
    (``"same_file"``, ``"cross_file"``, or ``"external"``)."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    groups = await _references(sym, file_path, workspace)
    compacted, _total, info_msg = _maybe_compact(groups, max_sites=max_sites)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "references": compacted,
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    if max_sites != 50:
        result["query"]["max"] = max_sites
    result["meta"] = _make_meta(
        ws_rel, lsp=sym.lsp_server, language=sym.language, info=info_msg,
    )
    return result


async def file_overview(
    file_path: str | Path,
    *,
    depth: int = 0,
    workspace: Path | None = None,
    command: str = "overview",
) -> dict:
    """Build a file overview ToC with signatures and reference counts.

    Returns ``file``, ``imports`` (top-level only, each with
    ``{line, statement, lazy}``), ``symbols``, ``symbol_count``,
    ``depth``, and ``query``."""
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await _overview(file_path, depth=depth, workspace=workspace)
    overview_server = result.pop("_server", "")
    overview_language = result.pop("_language", "")
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), depth=depth,
    )
    result["meta"] = _make_meta(ws_rel, lsp=overview_server, language=overview_language)
    return result


async def explain_symbol(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    max_sites: int = 100,
    workspace: Path | None = None,
    command: str = "explain",
) -> dict:
    """Full symbol report: body, definers, callers, callees, references.

    Body text is truncated at 6000 characters (with a truncation note)
    to keep responses agent-friendly.  Call and reference entries include
    a ``locality`` field.

    *max_sites* controls the **total** site budget across all three
    sub-lists (incoming calls, outgoing calls, references).  It is divided
    evenly: each sub-list gets ``max_sites // 3``.  Default 100 means
    ~33 sites per sub-list before compaction kicks in.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = await _explain(sym, file_path, workspace)

    # Each sub-list gets an even share of the total site budget.
    per_list = max_sites // 3

    # Apply compaction to sub-lists; merge info messages.
    infos: list[str] = []
    result["incoming_calls"], _, ic_info = _maybe_compact(
        result["incoming_calls"], max_sites=per_list,
    )
    result["outgoing_calls"], _, oc_info = _maybe_compact(
        result["outgoing_calls"], max_sites=per_list,
    )
    result["references"], _, ref_info = _maybe_compact(
        result["references"], max_sites=per_list,
    )
    for msg in (ic_info, oc_info, ref_info):
        if msg:
            infos.append(msg)
    explain_info = "; ".join(infos) if infos else None
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line,
    )
    if max_sites != 100:
        result["query"]["max"] = max_sites
    result["meta"] = _make_meta(
        ws_rel, lsp=sym.lsp_server, language=sym.language, info=explain_info,
    )
    return result


async def search_symbols(
    query: str,
    *,
    kind: str | None = None,
    limit: int = 40,
    workspace: Path | None = None,
    path_filter: str | None = None,
    command: str = "search",
) -> dict:
    """Search the workspace for symbols matching *query*.

    Parameters
    ----------
    limit : int
        Max results to return (default 40).  When results are capped,
        ``meta.info`` carries a human-readable message.
    path_filter : str or None
        Only return results whose relative file path contains this
        substring (e.g. ``"codebase/"``, ``"_resolve.py"``).
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await _search(
        query, kind=kind, limit=limit, workspace=workspace, path_filter=path_filter,
    )
    search_server = result.pop("_server", "")
    search_language = result.pop("_language", "")
    search_info = result.pop("_info_msg", None)
    result["query"] = _make_query(command, arg=query, kind=kind, limit=limit)
    if path_filter:
        result["query"]["path"] = path_filter
    result["meta"] = _make_meta(
        ws_rel, lsp=search_server, language=search_language, info=search_info,
    )
    return result


async def analyze_impact(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    depth: int = 10,
    max_sites: int = 100,
    workspace: Path | None = None,
    command: str = "impact",
) -> dict:
    """Change impact: symbol-level LSP callers + file-level import graph blast radius.

    Parameters
    ----------
    depth : int
        How many import hops for the file-level ``dependents`` (default 10).
    max_sites : int
        Total site budget across the three symbol-level sub-lists
        (incoming calls, outgoing calls, references).  Divided evenly:
        each sub-list gets ``max_sites // 3``.  Default 100 means ~33
        sites per sub-list before compaction.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = await _impact(sym, file_path, workspace, depth=depth)

    # Each sub-list gets an even share of the total site budget.
    per_list = max_sites // 3

    # Apply compaction to symbol_level sub-lists.
    sl = result["symbol_level"]
    infos: list[str] = []
    sl["incoming_calls"], _, ic_info = _maybe_compact(
        sl["incoming_calls"], max_sites=per_list,
    )
    sl["outgoing_calls"], _, oc_info = _maybe_compact(
        sl["outgoing_calls"], max_sites=per_list,
    )
    sl["references"], _, ref_info = _maybe_compact(
        sl["references"], max_sites=per_list,
    )
    for msg in (ic_info, oc_info, ref_info):
        if msg:
            infos.append(msg)
    impact_info = "; ".join(infos) if infos else None
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
        symbol=symbol_name, line=line, depth=depth,
    )
    if max_sites != 100:
        result["query"]["max"] = max_sites
    result["meta"] = _make_meta(
        ws_rel, lsp=sym.lsp_server, language=sym.language, info=impact_info,
    )
    return result


async def find_definition(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "definition",
) -> dict:
    """Return the definition and type-definition sites of *symbol_name*.

    ``definition`` is the first (primary) definer site with
    ``{file, line, snippet, locality}``, or ``null`` when there is no
    workspace-local definition.  ``type_definition`` is the type's
    definition site (same shape), or ``null`` for primitives, built-ins,
    or when the type is external.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    def_data = await _definition(sym, file_path, workspace)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "definition": def_data["definers"][0] if def_data["definers"] else None,
        "type_definition": def_data["type_definition"],
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), symbol=symbol_name, line=line,
    )
    result["meta"] = _make_meta(ws_rel, lsp=sym.lsp_server, language=sym.language)
    return result


async def hover_symbol(
    file_path: str | Path,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
    command: str = "hover",
) -> dict:
    """Return hover info (signature + docstring as markdown) for *symbol_name*.

    The ``hover`` field contains the raw LSP hover markdown — agents
    natively understand this format.  ``null`` if no hover info is
    available (e.g. built-ins without docstrings).
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    sym = await resolve_symbol(file_path, symbol_name, line=line, workspace=workspace)
    result = {
        "symbol": sym.name,
        "kind": sym.kind,
        "hover": await _hover(sym, file_path, workspace),
    }
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), symbol=symbol_name, line=line,
    )
    result["meta"] = _make_meta(ws_rel, lsp=sym.lsp_server, language=sym.language)
    return result


async def file_diagnostics(
    file_path: str | Path,
    *,
    max_results: int = 50,
    workspace: Path | None = None,
    command: str = "diagnostics",
) -> dict:
    """Return diagnostics for *file_path* with snippets and severity counts.

    Diagnostics are sorted by severity (errors first) then by line number.
    Each diagnostic includes a one-line 200-char snippet.  ``counts``
    reflects the full totals regardless of *max_results*.
    """
    from lsp import detect_workspace
    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    fp = Path(file_path).resolve()
    result = await _diagnostics(fp, workspace=workspace, max_results=max_results)
    # Pop internal fields before building meta.
    diag_lsp = result.pop("lsp", "")
    diag_language = result.pop("_language", "")
    lsp_meta = diag_lsp if diag_lsp else None
    lang_meta = diag_language if diag_language else None
    result["query"] = _make_query(
        command, file=relativize(fp, ws_rel), max=max_results,
    )
    result["meta"] = _make_meta(ws_rel, lsp=lsp_meta, language=lang_meta)
    return result


# ── Import-graph tools ─────────────────────────────────────────────────────────


async def architecture(
    *,
    hotspots: int = 20,
    workspace: Path | None = None,
    command: str = "architecture",
) -> dict:
    """Repo architecture: directory-level import graph, entry points, hotspots.

    Pure import-graph computation — zero LSP calls.  Returns a
    high-level structural view useful for onboarding an agent to a
    codebase it has never seen before.

    *hotspots* controls how many high-impact files are ranked (default 20).
    """
    from lsp import query_architecture, detect_workspace

    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await query_architecture(hotspots=hotspots, workspace=workspace)
    result["query"] = _make_query(command)
    if hotspots != 20:
        result["query"]["hotspots"] = hotspots
    result["meta"] = _make_meta(ws_rel)
    return result


async def import_dependents(
    file_path: str | Path,
    *,
    depth: int = 1,
    workspace: Path | None = None,
    command: str = "import-dependents",
) -> dict:
    """Return files that (transitively) import *file_path*.

    Uses the import graph maintained by the daemon — zero LSP queries.
    Each entry includes ``file`` and ``depth``.
    """
    from lsp import detect_workspace
    from lsp import query_import_dependents

    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await query_import_dependents(
        Path(file_path), depth=depth, workspace=workspace,
    )
    # Polish: remove internal keys.
    result.pop("depth", None)
    result.pop("file", None)
    result.pop("workspace", None)
    graph_info = _format_info(result.pop("info", {}))
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), depth=depth,
    )
    result["meta"] = _make_meta(ws_rel, info=graph_info)
    return result


async def import_dependencies(
    file_path: str | Path,
    *,
    workspace: Path | None = None,
    command: str = "import-dependencies",
) -> dict:
    """Return the files that *file_path* directly imports."""
    from lsp import detect_workspace
    from lsp import query_import_dependencies

    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await query_import_dependencies(
        Path(file_path), workspace=workspace,
    )
    # Polish: remove internal keys.
    result.pop("file", None)
    result.pop("workspace", None)
    graph_info = _format_info(result.pop("info", {}))
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel),
    )
    result["meta"] = _make_meta(ws_rel, info=graph_info)
    return result


async def affected_test_files(
    file_path: str | Path,
    *,
    depth: int = 10,
    workspace: Path | None = None,
    command: str = "affected-tests",
) -> dict:
    """Return test files that (transitively) import *file_path*."""
    from lsp import detect_workspace
    from lsp import query_import_affected_tests

    ws_rel = workspace or Path.cwd()
    ws_rel = detect_workspace(ws_rel)
    result = await query_import_affected_tests(
        Path(file_path), depth=depth, workspace=workspace,
    )
    # Polish: remove internal keys.
    result.pop("depth", None)
    result.pop("file", None)
    result.pop("workspace", None)
    graph_info = _format_info(result.pop("info", {}))
    result["query"] = _make_query(
        command, file=relativize(file_path, ws_rel), depth=depth,
    )
    result["meta"] = _make_meta(ws_rel, info=graph_info)
    return result
