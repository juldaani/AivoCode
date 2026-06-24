"""Analyze symbols — call hierarchy, references, overview, explain.

Why this exists
- The ``codebase`` commands ``incoming-calls``, ``outgoing-calls``,
  ``references``, ``overview``, and ``explain`` all compose LSP primitives
  with file reading.  This module provides the shared building blocks so
  each command is a thin wrapper around a single public function.

All public functions are async — they ``await`` LSP calls from within
the FastAPI event loop.
"""

from __future__ import annotations

from pathlib import Path

from codebase._read import _extract_imports
from codebase._treesitter import _get_parser
from codebase._resolve import ResolvedSymbol, _symbol_tree_by_depth, relativize
from codebase._snippet import read_range, read_snippet_chars


# Only include callable/type-defining symbols in overviews.
_OVERVIEW_KINDS: frozenset[str] = frozenset(
    {
        "Function", "Method", "Constructor",
        "Class", "Interface", "Struct",
        "Enum", "Event",
    }
)


# ── Per-site helpers ───────────────────────────────────────────────────────────


def _build_site(
    file_uri: str,
    line: int,
    workspace_root: Path,
    symbol_info: dict | None = None,
    source_file: Path | None = None,
) -> dict:
    """Build a reference/call site entry with optional locality tagging.

    When *source_file* is provided, a ``locality`` field is added:
    ``"same_file"``, ``"cross_file"`` (within workspace), or ``"external"``
    (outside workspace).
    """
    file_path = _uri_to_path(file_uri)
    try:
        rel = str(Path(file_path).relative_to(workspace_root))
        in_workspace = True
    except ValueError:
        rel = file_path
        in_workspace = False

    entry: dict = {
        "file": rel,
        "line": line,
        "snippet": read_snippet_chars(file_path, line),
    }
    if symbol_info:
        entry["symbol"] = symbol_info["name"]
        entry["kind"] = symbol_info["kind"]

    if source_file is not None:
        if in_workspace:
            if Path(file_path).resolve() == source_file.resolve():
                entry["locality"] = "same_file"
            else:
                entry["locality"] = "cross_file"
        else:
            entry["locality"] = "external"

    return entry


def _uri_to_path(uri: str) -> str:
    if uri.startswith("file://"):
        return uri[len("file://"):]
    return uri


def _extract_line(pos_dict: dict) -> int:
    return pos_dict.get("start", {}).get("line", 1)


# ── Site grouping ───────────────────────────────────────────────────────────────


def _group_sites(sites: list[dict]) -> list[dict]:
    """Group a flat list of ``{file, line, snippet, ...}`` entries by file.

    Each resulting group has ``{file, locality, count, sites}`` where
    ``sites`` is the per-line detail (without the redundant ``file`` and
    ``locality`` keys).  Groups are ordered by first sighting.
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for site in sites:
        f = site.get("file", "")
        if f not in groups:
            groups[f] = {
                "file": f,
                "locality": site.get("locality", "cross_file"),
                "count": 0,
                "sites": [],
            }
            order.append(f)
        entry = dict(site)
        entry.pop("file", None)
        entry.pop("locality", None)
        groups[f]["sites"].append(entry)
        groups[f]["count"] += 1
    return [groups[f] for f in order]


def _maybe_compact(
    groups: list[dict],
    *,
    max_sites: int = 100,
    per_file_n: int = 10,
) -> tuple[list[dict], int, str | None]:
    """Apply Rule E compaction when total sites exceed *max_sites*.

    Each group keeps the first *per_file_n* entries with snippets in
    ``sites`` and the remainder as bare line numbers in ``lines``.
    Groups with ``count <= per_file_n`` are left untouched (all in
    ``sites``, no ``lines`` key).

    Returns ``(groups, total, info_msg)`` — *info_msg* is ``None`` when
    no compaction was necessary **or** when the total exceeded the cap
    but no per-file group actually triggered (all within *per_file_n*).
    """
    total_sites = sum(g["count"] for g in groups)
    if total_sites <= max_sites:
        return groups, total_sites, None

    file_count = len(groups)
    sites_snippets = 0
    lines_count = 0

    for g in groups:
        g_sites = g.get("sites", [])
        if len(g_sites) > per_file_n:
            sites_snippets += per_file_n
            g["lines"] = [s["line"] for s in g_sites[per_file_n:]]
            g["sites"] = g_sites[:per_file_n]
            lines_count += len(g["lines"])
        else:
            sites_snippets += len(g_sites)

    # Only report compaction when at least one group generated line numbers.
    if lines_count == 0:
        return groups, total_sites, None

    info_msg = (
        f"{total_sites} sites across {file_count} files "
        f"({sites_snippets} with snippets, {lines_count} as line numbers).  "
        f"per file: first {per_file_n} sites shown with snippets, "
        f"remaining positions given as line numbers (use 'read' on any line "
        f"for full context)."
    )
    return groups, total_sites, info_msg


# ── Call hierarchy ─────────────────────────────────────────────────────────────


async def _incoming_calls(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> list[dict]:
    """Return call sites grouped by file.

    Each group has ``{file, locality, count, sites: [{line, snippet, symbol, kind}]}``.
    """
    from lsp import query_call_hierarchy_incoming, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()
    result = await query_call_hierarchy_incoming(
        fp,
        line=symbol.line,
        character=symbol.character,
        workspace=ws,
    )
    if "error" in result or result.get("result") is None:
        return []

    calls: list[dict] = result.get("result", [])
    sites: list[dict] = []
    for call in calls:
        from_ = call.get("from_", {})
        name = from_.get("name", "")
        kind = from_.get("kind", "Function")
        from_ranges = call.get("from_ranges", [])
        uri = from_.get("uri", "")
        if from_ranges:
            for fr in from_ranges:
                line = _extract_line(fr)
                sites.append(_build_site(
                    uri, line, ws,
                    {"kind": kind, "name": name},
                    source_file=fp,
                ))
    return _group_sites(sites)


async def _outgoing_calls(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
    *,
    workspace_only: bool = True,
) -> list[dict]:
    """Return call sites grouped by file.

    When ``workspace_only`` is ``True`` (default), calls to external
    locations (stdlib, site-packages) are excluded.  Each group has
    ``{file, locality, count, sites: [{line, snippet, symbol, kind}]}``.
    """
    from lsp import query_call_hierarchy_outgoing, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()
    result = await query_call_hierarchy_outgoing(
        fp,
        line=symbol.line,
        character=symbol.character,
        workspace=ws,
    )
    if "error" in result or result.get("result") is None:
        return []

    calls: list[dict] = result.get("result", [])
    sites: list[dict] = []
    for call in calls:
        to_ = call.get("to", {})
        name = to_.get("name", "")
        kind = to_.get("kind", "Function")
        uri = to_.get("uri", "")
        to_range = to_.get("range", {})
        to_line = _extract_line(to_range)
        site = _build_site(
            uri, to_line, ws,
            {"kind": kind, "name": name},
            source_file=fp,
        )
        if workspace_only and site.get("locality") == "external":
            continue
        sites.append(site)
    return _group_sites(sites)


# ── References ─────────────────────────────────────────────────────────────────


async def _references(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> list[dict]:
    """Return all reference sites for *symbol* (includes definition).

    Grouped by file: ``{file, locality, count, sites: [{line, snippet}]}``.
    """
    from lsp import query_references, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()
    result = await query_references(
        fp,
        line=symbol.line,
        character=symbol.character,
        workspace=ws,
    )
    if "error" in result or result.get("result") is None:
        return []

    refs: list[dict] = result.get("result", [])
    sites: list[dict] = []
    for ref in refs:
        uri = ref.get("uri", "")
        line = _extract_line(ref.get("range", {}))
        sites.append(_build_site(uri, line, ws, source_file=fp))
    return _group_sites(sites)


# ── Overview ───────────────────────────────────────────────────────────────────


async def _overview(
    file_path: str | Path,
    depth: int = 0,
    workspace: Path | None = None,
) -> dict:
    """Build a ToC of callable/type-defining symbols in *file_path*.

    Returns ``{file, imports, symbols, symbol_count, depth}`` where
    ``imports`` contains top-level import statements only
    (``{line, statement, lazy: false}``).
    """
    from lsp import query_document_symbols, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    result = await query_document_symbols(fp, workspace=ws)
    if "error" in result:
        return {"error": result["error"], "symbols": [], "symbol_count": 0}

    symbols: list[dict] = result.get("symbols", [])
    tree = _symbol_tree_by_depth(symbols, depth, kind_filter=_OVERVIEW_KINDS)
    processed = await _process_overview_symbols(tree, fp, ws)
    return {
        "imports": _extract_imports(fp),
        "symbols": processed,
        "symbol_count": len(processed),
        "_server": result.get("server", ""),
        "_language": result.get("language", ""),
    }


async def _process_overview_symbols(
    symbols: list[dict],
    file_path: Path,
    workspace: Path,
) -> list[dict]:
    from lsp import query_references

    enriched: list[dict] = []
    for sym in symbols:
        kind = sym.get("kind", "")
        if kind not in _OVERVIEW_KINDS:
            continue

        line = sym.get("line", 1)
        if line is None:
            enriched.append(_empty_overview_entry(sym))
            continue

        range_start = sym.get("range_start", (line, 1))
        range_end = sym.get("range_end", (line, 1))
        sig_line = _extract_signature(file_path, range_start[0], line)
        sig_end_line = max(sig_line, range_start[0])
        preview = read_range(file_path, sig_end_line + 1, min(sig_end_line + 5, range_end[0]))

        ref_counts: dict[str, int] = {}
        try:
            refs = await query_references(
                file_path,
                line=sym["line"],
                character=sym.get("character", 1),
                workspace=workspace,
            )
            if "result" in refs:
                same_file = str(file_path.resolve())
                for ref in refs["result"]:
                    uri = ref.get("uri", "")
                    rpath = _uri_to_path(uri)
                    ref_line = _extract_line(ref.get("range", {}))
                    if rpath == same_file and ref_line == line:
                        continue
                    try:
                        rel = str(Path(rpath).relative_to(workspace))
                    except ValueError:
                        rel = rpath
                    ref_counts[rel] = ref_counts.get(rel, 0) + 1
        except Exception:
            pass

        entry = {
            "symbol": sym["name"],
            "kind": sym["kind"],
            "signature": _sig_line_text(file_path, range_start[0], sig_end_line),
            "preview": preview[:400] if preview else "",
            "range_line_char": {"start": list(range_start), "end": list(range_end)},
            "references_count": ref_counts,
        }
        children = sym.get("children")
        if children is None:
            entry["children"] = None
        elif isinstance(children, dict):
            # Depth-limited count marker from _symbol_tree_by_depth.
            entry["children"] = children
        else:
            processed = await _process_overview_symbols(children, file_path, workspace)
            entry["children"] = processed if processed else None
        enriched.append(entry)

    return enriched


def _empty_overview_entry(sym: dict) -> dict:
    return {
        "symbol": sym.get("name", ""),
        "kind": sym.get("kind", ""),
        "signature": "",
        "preview": "",
        "range_line_char": {"start": [1, 1], "end": [1, 1]},
        "references_count": {},
        "children": None,
    }


def _extract_signature(file_path: Path, range_start_line: int, sel_start_line: int) -> int:
    """Return the line number of the signature/header end for a symbol.

    Uses tree-sitter to determine whether *range_start_line* is inside a
    callable definition (function / class / interface / enum / struct), then
    finds the colon (Python) or brace (TypeScript) that terminates the header.
    Non-callable symbols (variables, constants) return *range_start_line*
    unchanged.

    The result is 1-indexed and used to split the symbol text into
    ``signature`` (``range_start_line .. result``) and ``body``
    (``result + 1 .. range_end``).
    """
    parser = _get_signature_parser(file_path)
    if parser is None:
        # No parser for this language — fall back to range bounds.
        return range_start_line

    try:
        source = file_path.read_bytes()
    except OSError:
        return range_start_line

    tree = parser.parse(source)

    # Locate the tree-sitter node at the symbol's range start.
    target_row = range_start_line - 1  # 1-indexed → 0-indexed
    point = (target_row, 0)
    node = tree.root_node.descendant_for_point_range(point, point)
    if node is None:
        return range_start_line

    # Definition node types that we consider "callable" for the purpose
    # of signature extraction.
    _DEFINITION_TYPES: tuple[str, ...] = (
        "function_definition",
        "class_definition",
        "decorated_definition",
        "function_declaration",
        "class_declaration",
        "method_definition",
        "abstract_class_declaration",
        "interface_declaration",
        "enum_declaration",
        "struct_item",        # Rust via tree-sitter-rust
        "impl_item",          # Rust
    )

    # Walk up to the enclosing definition node.
    def_node = node
    while def_node is not None:
        if def_node.type in _DEFINITION_TYPES:
            break
        def_node = def_node.parent

    if def_node is None:
        return range_start_line  # not inside a callable definition

    # Find the header terminator token: ':' for Python, '{' for C-family.
    _HEADER_TERMINATORS = frozenset({":", "{"})

    def _find_terminator(n) -> int | None:
        for child in n.children:
            if child.type in _HEADER_TERMINATORS:
                return child.start_point[0] + 1  # 0-indexed → 1-indexed
            result = _find_terminator(child)
            if result is not None:
                return result
        return None

    header_end = _find_terminator(def_node)
    if header_end is not None:
        return max(header_end, range_start_line)

    # Fallback: use the definition node's end line.
    return max(def_node.end_point[0] + 1, range_start_line)


def _sig_line_text(file_path: Path, start_line: int, end_line: int) -> str:
    return read_range(file_path, start_line, end_line)


# ── Language detection for tree-sitter ─────────────────────────────────────────


_SUFFIX_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
}


def _language_from_suffix(file_path: Path) -> str:
    """Map a file suffix to a tree-sitter language name."""
    return _SUFFIX_TO_LANGUAGE.get(file_path.suffix, "python")


def _get_signature_parser(file_path: Path):
    """Return a tree-sitter ``Parser`` for *file_path*, or ``None``."""
    language = _language_from_suffix(file_path)
    return _get_parser(language)


# ── Explain ────────────────────────────────────────────────────────────────────


async def _explain(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict:
    """Full symbol report: body, definers, incoming/outgoing calls, references.

    Body text is truncated at 6000 characters with a truncation note
    appended when the source exceeds that threshold.  Call and reference
    entries include a ``locality`` field.
    """
    from lsp import query_definition, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    body = read_range(fp, symbol.range_start[0], symbol.range_end[0])
    # Truncate huge bodies (e.g. large classes) to keep agent-friendly.
    max_chars = 6000
    if len(body) > max_chars:
        remaining = len(body) - max_chars
        body = f"{body[:max_chars]}\n... [truncated at {max_chars} chars, {remaining} more chars not shown]"

    # Definition.
    definers: list[dict] = []
    try:
        def_result = await query_definition(
            fp, line=symbol.line, character=symbol.character, workspace=ws,
        )
        if "result" in def_result:
            locs = def_result["result"]
            if locs is None:
                locs = []
            elif isinstance(locs, dict):
                locs = [locs]
            for loc in locs:
                uri = loc.get("uri", "")
                def_line = _extract_line(loc.get("range", {}))
                definers.append(_build_site(
                    uri, def_line, ws,
                    {"kind": symbol.kind, "name": symbol.name},
                ))
    except Exception:
        pass

    incoming = await _incoming_calls(symbol, fp, ws)
    outgoing = await _outgoing_calls(symbol, fp, ws)
    refs = await _references(symbol, fp, ws)

    return {
        "symbol": symbol.name,
        "kind": symbol.kind,
        "body": body,
        "range_line_char": {"start": list(symbol.range_start), "end": list(symbol.range_end)},
        "definers": definers,
        "incoming_calls": incoming,
        "outgoing_calls": outgoing,
        "references": refs,
    }


# ── Search ─────────────────────────────────────────────────────────────────────


async def _search(
    query: str,
    kind: str | None = None,
    limit: int = 40,
    workspace: Path | None = None,
    path_filter: str | None = None,
) -> dict:
    from lsp import query_workspace_symbol, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    result = await query_workspace_symbol(query, workspace=ws)

    if "error" in result or result.get("symbols") is None:
        return {
            "query": query, "results": [], "count": 0,
            "_server": result.get("server", ""), "_language": result.get("language", ""),
        }

    results: list[dict] = []
    total_matched: int = 0  # all that matched kind + path (before limit)
    for sym in result["symbols"]:
        sym_kind = sym.get("kind", "")
        if kind is not None and sym_kind.lower() != kind.lower():
            continue
        loc = sym.get("location", {})
        uri = loc.get("uri", "")
        file_path = _uri_to_path(uri)
        try:
            rel = str(Path(file_path).relative_to(ws))
        except ValueError:
            rel = file_path
        if path_filter is not None and path_filter not in rel:
            continue
        total_matched += 1
        line = _extract_line(loc.get("range", {}))
        entry: dict = {
            "symbol": sym.get("name", ""),
            "kind": sym_kind,
            "file": rel,
            "line": line,
        }
        container = sym.get("container_name")
        if container:
            entry["container"] = container
        if len(results) >= limit:
            continue
        results.append(entry)

    # Build info message when capped.
    info_msg: str | None = None
    if total_matched > limit:
        parts: list[str] = []
        if kind is not None:
            parts.append(f"kind={kind}")
        if path_filter is not None:
            parts.append(f"path='{path_filter}'")
        filter_str = (", ".join(parts) + ", ") if parts else ""
        info_msg = (
            f"{len(results)} of {total_matched} results shown "
            f"({filter_str}capped at limit {limit}) — "
            f"increase --limit or narrow with --path / --kind to see more"
        )

    return {
        "query": query,
        "results": results,
        "count": len(results),
        "_server": result.get("server", ""),
        "_language": result.get("language", ""),
        "_info_msg": info_msg,
    }


# ── Impact ─────────────────────────────────────────────────────────────────────


async def _impact(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
    depth: int = 10,
) -> dict:
    """Change impact: symbol-level LSP callers + file-level import graph blast radius.

    Composes two views of impact:
    1. ``symbol_level`` — immediate callers, callees, and references from LSP
       (depth 1, precise, symbol-aware).
    2. ``file_level`` — transitive file dependents from the tree-sitter import
       graph (configurable *depth*, zero LSP cost).  Includes test files.

    Together they answer "what breaks if I change this symbol?" — the LSP
    part for surgical precision and the import graph part for the full blast
    radius.
    """
    from lsp import detect_workspace
    from lsp import query_import_dependents

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    incoming = await _incoming_calls(symbol, fp, ws)
    outgoing = await _outgoing_calls(symbol, fp, ws)
    refs = await _references(symbol, fp, ws)

    # File-level transitive dependents from the import graph (zero LSP).
    deps_result = await query_import_dependents(fp, depth=depth, workspace=ws)

    return {
        "symbol": symbol.name,
        "kind": symbol.kind,
        "symbol_level": {
            "incoming_calls": incoming,
            "outgoing_calls": outgoing,
            "references": refs,
        },
        "file_level": {
            "dependents": deps_result.get("dependents", []),
        },
    }


# ── Definition ──────────────────────────────────────────────────────────────────


async def _definition(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict | None:
    """Return the definition site of *symbol* with snippet and locality.

    Returns a single ``{file, line, snippet, locality}`` dict, or ``None``
    if the symbol has no workspace-local definition (e.g. built-in or
    external library).
    """
    from lsp import query_definition, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    result = await query_definition(
        fp, line=symbol.line, character=symbol.character, workspace=ws,
    )
    locations: list[dict] = result.get("result") or []
    if not locations:
        return None

    loc = locations[0]
    uri = loc.get("uri", "")
    start = loc.get("range", {}).get("start", {})
    line = (start.get("line", 0) or 0) + 1  # LSP 0-indexed → 1-indexed

    return _build_site(uri, line, ws, source_file=fp)


# ── Hover ───────────────────────────────────────────────────────────────────────


async def _hover(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> str | None:
    """Return the hover markdown string for *symbol*, or ``None``."""
    from lsp import query_hover, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    result = await query_hover(
        fp, line=symbol.line, character=symbol.character, workspace=ws,
    )
    hover_data = result.get("result")
    if hover_data is None:
        return None
    return hover_data.get("value", "")


# ── Diagnostics ─────────────────────────────────────────────────────────────────


_SEVERITY_NAMES: dict[int, str] = {
    1: "Error",
    2: "Warning",
    3: "Information",
    4: "Hint",
}


async def _diagnostics(
    file_path: str | Path,
    workspace: Path | None = None,
    max_results: int = 50,
) -> dict:
    """Return diagnostics for *file_path* with snippets and severity counts.

    Each diagnostic is enriched with a one-line ``snippet`` (200 chars,
    same as other codebase tools).  Severity integers are converted to
    human-readable names.  Results are sorted by severity (errors first)
    then by line number.  The response includes full ``counts`` regardless
    of *max_results*.
    """
    from lsp import query_diagnostics, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    result = await query_diagnostics(fp, workspace=ws)
    raw_diags: list[dict] = result.get("diagnostics", [])
    raw_server: str = result.get("server", "")
    raw_language: str = result.get("language", "")

    # Group by severity — no snippets, just position + message.
    grouped: dict[str, list[dict]] = {"error": [], "warning": [], "information": [], "hint": []}
    counts: dict[str, int] = {"error": 0, "warning": 0, "information": 0, "hint": 0}

    for d in raw_diags:
        sev_int = d.get("severity", 1)
        sev_name = _SEVERITY_NAMES.get(sev_int, "Error")
        key = sev_name.lower()
        counts[key] += 1

        start = d.get("range", {}).get("start", {})
        line = (start.get("line", 0) or 0) + 1
        character = (start.get("character", 0) or 0) + 1

        grouped[key].append({
            "message": d.get("message", ""),
            "line": line,
            "character": character,
        })

    # Respect max_results: truncate each group proportionally.
    remaining = max_results
    for key in ("error", "warning", "information", "hint"):
        if remaining <= 0:
            grouped[key] = []
        elif len(grouped[key]) > remaining:
            grouped[key] = grouped[key][:remaining]
        remaining -= len(grouped[key])

    return {
        "lsp": raw_server,
        "diagnostics": grouped,
        "counts": counts,
        "_language": raw_language,
    }
