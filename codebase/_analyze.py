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

from codebase._resolve import ResolvedSymbol, _symbol_tree_by_depth, relativize
from codebase._snippet import read_range, read_snippet_chars


# ── Per-site helpers ───────────────────────────────────────────────────────────


def _build_site(
    file_uri: str,
    line: int,
    workspace_root: Path,
    symbol_info: dict | None = None,
) -> dict:
    file_path = _uri_to_path(file_uri)
    try:
        rel = str(Path(file_path).relative_to(workspace_root))
    except ValueError:
        rel = file_path

    entry: dict = {
        "file": rel,
        "line": line,
        "snippet": read_snippet_chars(file_path, line),
    }
    if symbol_info:
        entry["symbol"] = symbol_info["name"]
        entry["kind"] = symbol_info["kind"]
    return entry


def _uri_to_path(uri: str) -> str:
    if uri.startswith("file://"):
        return uri[len("file://"):]
    return uri


def _extract_line(pos_dict: dict) -> int:
    return pos_dict.get("start", {}).get("line", 1)


# ── Call hierarchy ─────────────────────────────────────────────────────────────


async def _incoming_calls(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> list[dict]:
    from lsp import query_call_hierarchy_incoming, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    result = await query_call_hierarchy_incoming(
        Path(file_path),
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
                ))
    return sites


async def _outgoing_calls(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> list[dict]:
    from lsp import query_call_hierarchy_outgoing, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    result = await query_call_hierarchy_outgoing(
        Path(file_path),
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
        sites.append(_build_site(
            uri, to_line, ws,
            {"kind": kind, "name": name},
        ))
    return sites


# ── References ─────────────────────────────────────────────────────────────────


async def _references(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> list[dict]:
    from lsp import query_references, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    result = await query_references(
        Path(file_path),
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
        sites.append(_build_site(uri, line, ws))
    return sites


# ── Overview ───────────────────────────────────────────────────────────────────


async def _overview(
    file_path: str | Path,
    depth: int = 0,
    workspace: Path | None = None,
) -> dict:
    from lsp import query_document_symbols, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    result = await query_document_symbols(fp, workspace=ws)
    if "error" in result:
        return {"error": result["error"], "file": str(fp), "symbols": [], "symbol_count": 0, "depth": depth}

    symbols: list[dict] = result.get("symbols", [])
    tree = _symbol_tree_by_depth(symbols, depth)
    processed = await _process_overview_symbols(tree, fp, ws)
    return {
        "file": relativize(fp, ws),
        "symbols": processed,
        "symbol_count": len(processed),
        "depth": depth,
    }


async def _process_overview_symbols(
    symbols: list[dict],
    file_path: Path,
    workspace: Path,
) -> list[dict]:
    from lsp import query_references

    # Only include callable/type-defining symbols in overviews.
    _OVERVIEW_KINDS: frozenset[str] = frozenset(
        {
            "Function", "Method", "Constructor",
            "Class", "Interface", "Struct",
            "Enum", "Event",
        }
    )

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
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return range_start_line

    if range_start_line < 1 or range_start_line > len(lines):
        return range_start_line

    first_line = lines[range_start_line - 1].strip()

    # Only scan forward for def / class / decorator constructs.
    # Everything else (variables, constants, etc.) → just that one line.
    is_callable = (
        first_line.startswith("def ")
        or first_line.startswith("async def ")
        or first_line.startswith("class ")
        or first_line.startswith("@")
    )
    if not is_callable:
        return range_start_line

    for i in range(range_start_line - 1, len(lines)):
        actual_line = i + 1
        stripped = lines[i].strip()
        if actual_line >= sel_start_line and stripped.endswith(":"):
            return actual_line
        if actual_line > sel_start_line and not stripped:
            return actual_line

    return range_start_line


def _sig_line_text(file_path: Path, start_line: int, end_line: int) -> str:
    return read_range(file_path, start_line, end_line)


# ── Explain ────────────────────────────────────────────────────────────────────


async def _explain(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict:
    from lsp import query_definition, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    body = read_range(fp, symbol.range_start[0], symbol.range_end[0])

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
        "file": relativize(fp, ws),
        "definers": definers,
        "incoming_calls": incoming,
        "outgoing_calls": outgoing,
        "references": refs,
    }


# ── Search ─────────────────────────────────────────────────────────────────────


async def _search(
    query: str,
    kind: str | None = None,
    limit: int = 50,
    workspace: Path | None = None,
) -> dict:
    from lsp import query_workspace_symbol, detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    result = await query_workspace_symbol(query, workspace=ws)

    if "error" in result or result.get("symbols") is None:
        return {"query": query, "results": [], "count": 0}

    results: list[dict] = []
    for sym in result["symbols"]:
        sym_kind = sym.get("kind", "")
        # Apply kind filter if specified.
        if kind is not None and sym_kind.lower() != kind.lower():
            continue
        loc = sym.get("location", {})
        uri = loc.get("uri", "")
        file_path = _uri_to_path(uri)
        try:
            rel = str(Path(file_path).relative_to(ws))
        except ValueError:
            rel = file_path
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
        results.append(entry)
        if len(results) >= limit:
            break

    return {"query": query, "results": results, "count": len(results)}


# ── Impact ─────────────────────────────────────────────────────────────────────


async def _impact(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict:
    """Change impact: incoming + outgoing calls + references."""
    from lsp import detect_workspace

    ws = workspace or Path.cwd()
    ws = detect_workspace(ws)
    fp = Path(file_path).resolve()

    incoming = await _incoming_calls(symbol, fp, ws)
    outgoing = await _outgoing_calls(symbol, fp, ws)
    refs = await _references(symbol, fp, ws)

    return {
        "symbol": symbol.name,
        "kind": symbol.kind,
        "file": relativize(fp, ws),
        "incoming_calls": incoming,
        "outgoing_calls": outgoing,
        "references": refs,
    }
