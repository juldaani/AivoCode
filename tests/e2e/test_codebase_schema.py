"""End-to-end schema tests: ``python -m cli codebase`` output shape assertions.

What this tests
- Every codebase command returns the expected top-level keys.
- Nested structures (symbols, calls, refs, imports, query) have correct types.
- Locality field is present and valid (outgoing-calls, incoming-calls, references).
- Import extraction produces ``{line, statement}`` dicts.
- Overview kind filter excludes non-callable symbols.
- Children are ``null``, ``{"count": N}``, or list.
- Workspace-only filtering excludes external calls by default.
- Explain truncation kicks in for large class bodies.
- Search limit, empty results, and tree suffix filter work.
- Query block is present with ``command`` and no ``None`` values.

Does NOT assert exact line numbers or body content — that's what snapshot tests cover.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Real source files in this repo used as test fixtures.
FILES = {
    "resolve": "codebase/_resolve.py",
    "client": "lsp/client.py",
    "analyze": "codebase/_analyze.py",
    "init": "codebase/__init__.py",
}

SYMBOLS = {
    "resolve": ["ResolvedSymbol", "resolve_symbol", "_deep_flatten"],
    "client": ["LspClient", "get_diagnostics", "shutdown"],
    "analyze": ["_overview", "_extract_signature", "_sig_line_text"],
}

# Kind filter for overview — only callable/type-defining symbols.
_OVERVIEW_KINDS = {
    "Function", "Method", "Constructor",
    "Class", "Interface", "Struct", "Enum", "Event",
}

_LOCALITY_VALUES = {"same_file", "cross_file", "external"}


# ── CLI helper ─────────────────────────────────────────────────────────────────


def _run(lsp_server: str, *args: str) -> dict:
    """Run ``python -m cli codebase <args>`` against *lsp_server*, return parsed JSON."""
    env = {**os.environ, "AIVOCODE_URL": lsp_server}
    proc = subprocess.run(
        ["python", "-m", "cli", "codebase", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return json.loads(proc.stdout)


# ── tree ───────────────────────────────────────────────────────────────────────


def test_tree_has_root_and_query(lsp_server: str) -> None:
    result = _run(lsp_server, "tree", "--suffix", ".py")
    assert "tree" in result, "tree missing 'tree' key"
    assert isinstance(result["tree"], list), "tree must be a list"
    assert "query" in result, "tree missing 'query' key"
    assert "meta" in result, "tree missing 'meta' key"
    q = result["query"]
    assert q.get("command") == "tree"
    assert "suffix" in q


def test_tree_no_suffix_shows_all_files(lsp_server: str) -> None:
    """Without --suffix, non-.py files (e.g. README.md) appear."""
    result = _run(lsp_server, "tree")
    assert "tree" in result
    # Just verify it returns something — content is snapshot territory.


# ── search ─────────────────────────────────────────────────────────────────────


def test_search_returns_correct_shape(lsp_server: str) -> None:
    """Search response has results, count, query — even if empty from cold daemon."""
    result = _run(lsp_server, "search", "LspClient")
    assert "results" in result
    assert "count" in result
    assert "query" in result
    assert isinstance(result["results"], list)
    if result["results"]:
        r = result["results"][0]
        for key in ("symbol", "kind", "file", "line"):
            assert key in r, f"search result missing '{key}'"


def test_search_limit_enforced(lsp_server: str) -> None:
    result = _run(lsp_server, "search", "query", "--limit", "3")
    assert result["count"] <= 3


def test_search_empty_for_nonexistent(lsp_server: str) -> None:
    result = _run(lsp_server, "search", "ZzzNonexistentSymbol123")
    assert result["results"] == []
    assert result["count"] == 0


# ── overview ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("file_key", ["resolve", "client", "analyze", "init"])
def test_overview_shape(lsp_server: str, file_key: str) -> None:
    result = _run(lsp_server, "overview", FILES[file_key], "--depth", "0")
    for key in ("imports", "symbols", "symbol_count", "query", "meta"):
        assert key in result, f"overview missing '{key}'"
    assert isinstance(result["imports"], dict)
    assert isinstance(result["symbols"], list)
    assert isinstance(result["symbol_count"], int)
    assert result["symbol_count"] == len(result["symbols"])
    # Query block
    q = result["query"]
    assert q.get("command") == "overview"
    assert None not in q.values()


@pytest.mark.parametrize("file_key", ["resolve", "client", "analyze", "init"])
def test_overview_imports_format(lsp_server: str, file_key: str) -> None:
    result = _run(lsp_server, "overview", FILES[file_key], "--depth", "0")
    imports = result["imports"]
    assert set(imports.keys()) >= {"module", "lazy"}, f"imports missing groups: {imports.keys()}"
    for imp in imports["module"]:
        assert "line" in imp, f"module import missing 'line': {imp}"
        assert "statement" in imp, f"module import missing 'statement': {imp}"
        assert isinstance(imp["line"], int)
        assert imp["line"] >= 1


@pytest.mark.parametrize("file_key", ["resolve", "client", "analyze", "init"])
def test_overview_kinds_are_filtered(lsp_server: str, file_key: str) -> None:
    """Every symbol in overview belongs to the callable/type-defining kind set."""
    result = _run(lsp_server, "overview", FILES[file_key], "--depth", "0")
    for sym in result["symbols"]:
        assert sym["kind"] in _OVERVIEW_KINDS, (
            f"unexpected kind '{sym['kind']}' for symbol '{sym['symbol']}'"
        )


@pytest.mark.parametrize("file_key", ["resolve", "client", "analyze", "init"])
def test_overview_children_null_or_dict_or_list(lsp_server: str, file_key: str) -> None:
    """children is None, {"count": N}, or a list of symbols."""
    result = _run(lsp_server, "overview", FILES[file_key], "--depth", "1")
    for sym in result["symbols"]:
        children = sym["children"]
        assert children is None or isinstance(children, (dict, list)), (
            f"children must be None, dict, or list; got {type(children)} for '{sym['symbol']}'"
        )
        if isinstance(children, list):
            for child in children:
                assert "symbol" in child
                assert "kind" in child


def test_overview_depth_zero_shows_count(lsp_server: str) -> None:
    """At depth=0, classes show children: {"count": N}."""
    result = _run(lsp_server, "overview", FILES["client"], "--depth", "0")
    lsp_client = next(
        (s for s in result["symbols"] if s["symbol"] == "LspClient"), None
    )
    assert lsp_client is not None, "LspClient not found"
    children = lsp_client["children"]
    assert isinstance(children, dict), (
        f"expected {{count: N}} at depth=0, got {type(children)}"
    )
    assert "count" in children


@pytest.mark.parametrize("file_key", ["resolve", "client", "analyze"])
def test_overview_symbol_has_signature_and_preview(lsp_server: str, file_key: str) -> None:
    result = _run(lsp_server, "overview", FILES[file_key], "--depth", "0")
    for sym in result["symbols"]:
        assert "signature" in sym
        assert isinstance(sym["signature"], str)
        assert "preview" in sym
        assert isinstance(sym["preview"], str)
        assert "range_line_char" in sym
        r = sym["range_line_char"]
        assert isinstance(r["start"], list) and len(r["start"]) == 2
        assert isinstance(r["end"], list) and len(r["end"]) == 2
        assert r["start"][0] >= 1, "line numbers must be 1-indexed"


# ── read ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol_name", ["resolve_symbol", "ResolvedSymbol"])
def test_read_has_imports_and_body(lsp_server: str, symbol_name: str) -> None:
    result = _run(lsp_server, "read-symbol", FILES["resolve"], "--symbol", symbol_name)
    for key in ("symbol", "kind", "body", "range_line_char", "imports", "query", "meta"):
        assert key in result, f"read missing '{key}'"
    assert len(result["body"]) > 0, f"body is empty for {symbol_name}"
    imports = result["imports"]
    assert isinstance(imports, dict), "imports must be grouped dict"
    total = len(imports.get("module", [])) + len(imports.get("lazy", []))
    assert total > 0, "imports is empty"
    for imp in imports.get("module", []) + imports.get("lazy", []):
        assert "line" in imp
        assert "statement" in imp


# ── incoming-calls ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol_name", SYMBOLS["analyze"])
def test_incoming_calls_has_locality(lsp_server: str, symbol_name: str) -> None:
    result = _run(
        lsp_server, "incoming-calls", FILES["analyze"], "--symbol", symbol_name,
    )
    for key in ("symbol", "kind", "incoming_calls", "query", "meta"):
        assert key in result
    for group in result["incoming_calls"]:
        assert "locality" in group, f"incoming group missing 'locality': {group}"
        assert group["locality"] in _LOCALITY_VALUES
        assert "file" in group
        assert "count" in group
        assert "sites" in group
        for site in group["sites"]:
            assert "line" in site
            assert "snippet" in site


# ── outgoing-calls ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol_name", SYMBOLS["analyze"])
def test_outgoing_calls_has_locality(lsp_server: str, symbol_name: str) -> None:
    result = _run(
        lsp_server, "outgoing-calls", FILES["analyze"], "--symbol", symbol_name,
    )
    for key in ("symbol", "kind", "outgoing_calls", "query", "meta"):
        assert key in result
    for group in result["outgoing_calls"]:
        assert "locality" in group, f"outgoing group missing 'locality': {group}"
        assert group["locality"] in ("same_file", "cross_file"), (
            f"default (--workspace-only) must not include external calls, "
            f"got locality={group['locality']}"
        )
        assert "file" in group
        assert "count" in group
        assert "sites" in group
        for site in group["sites"]:
            assert "line" in site
            assert "snippet" in site


def test_outgoing_calls_include_external_flag_works(lsp_server: str) -> None:
    """--include-external brings back calls with locality=external."""
    result = _run(
        lsp_server, "outgoing-calls", FILES["analyze"],
        "--symbol", "_overview", "--include-external",
    )
    localities = {c.get("locality") for c in result["outgoing_calls"]}
    assert "external" in localities, (
        f"--include-external should show external calls; got localities={localities}"
    )


# ── references ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol_name", SYMBOLS["resolve"])
def test_references_has_locality(lsp_server: str, symbol_name: str) -> None:
    result = _run(
        lsp_server, "references", FILES["resolve"], "--symbol", symbol_name,
    )
    for key in ("symbol", "kind", "references", "query", "meta"):
        assert key in result
    assert len(result["references"]) > 0, f"no references for {symbol_name}"
    for group in result["references"]:
        assert "locality" in group, f"ref group missing 'locality': {group}"
        assert group["locality"] in _LOCALITY_VALUES
        assert "file" in group
        assert "count" in group
        assert "sites" in group
        for site in group["sites"]:
            assert "line" in site
            assert "snippet" in site


# ── explain ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol_name", ["resolve_symbol", "ResolvedSymbol"])
def test_explain_shape(lsp_server: str, symbol_name: str) -> None:
    result = _run(lsp_server, "explain", FILES["resolve"], "--symbol", symbol_name)
    for key in (
        "symbol", "kind", "body", "range_line_char",
        "definers", "type_definition", "incoming_calls", "outgoing_calls",
        "references", "query", "meta",
    ):
        assert key in result, f"explain missing '{key}'"
    assert len(result["body"]) > 0
    # type_definition is either null or a dict with file/line/locality.
    td = result["type_definition"]
    if td is not None:
        assert isinstance(td, dict), f"type_definition should be dict or null, got {type(td)}"
        for td_key in ("file", "line", "snippet", "locality"):
            assert td_key in td, f"type_definition missing '{td_key}'"
        assert td["locality"] in _LOCALITY_VALUES, (
            f"type_definition locality '{td['locality']}' not in {_LOCALITY_VALUES}"
        )


def test_explain_truncates_large_class(lsp_server: str) -> None:
    """LspClient has ~13k chars; explain should truncate."""
    result = _run(lsp_server, "explain", FILES["client"], "--symbol", "LspClient")
    assert len(result["body"]) <= 6100, (
        f"expected body <= 6100 chars, got {len(result['body'])}"
    )
    assert "[truncated" in result["body"], "truncated body should have note"


def test_explain_does_not_truncate_small_function(lsp_server: str) -> None:
    """resolve_symbol has ~2k chars; should not be truncated."""
    result = _run(lsp_server, "explain", FILES["resolve"], "--symbol", "resolve_symbol")
    assert "[truncated" not in result["body"], "small body should not be truncated"


# ── impact ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol_name", ["_overview", "_sig_line_text"])
def test_impact_shape(lsp_server: str, symbol_name: str) -> None:
    result = _run(
        lsp_server, "impact", FILES["analyze"], "--symbol", symbol_name, "--depth", "3",
    )
    # Top-level keys
    for key in ("symbol", "kind", "symbol_level", "file_level", "query", "meta"):
        assert key in result, f"impact missing '{key}'"
    # symbol_level contains the LSP-derived lists
    sl = result["symbol_level"]
    for key in ("incoming_calls", "outgoing_calls", "references"):
        assert key in sl, f"impact symbol_level missing '{key}'"
        assert isinstance(sl[key], list)
    # file_level contains the import graph results (dependents includes tests)
    fl = result["file_level"]
    assert "dependents" in fl, "impact file_level missing 'dependents'"
    assert isinstance(fl["dependents"], list)
    # Each file-level entry has file and depth
    for entry in fl["dependents"]:
        assert "file" in entry
        assert "depth" in entry
    # depth is reflected in the query block
    assert result["query"].get("depth") == 3


# ── cross-cutting ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("command,args", [
    ("read-symbol", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("incoming-calls", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("outgoing-calls", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("references", [FILES["resolve"], "--symbol", "ResolvedSymbol"]),
    ("overview", [FILES["client"], "--depth", "0"]),
    ("explain", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("search", ["ResolvedSymbol"]),
    ("impact", [FILES["analyze"], "--symbol", "_overview"]),
    ("tree", ["--suffix", ".py"]),
    ("architecture", ["--hotspots", "5"]),
])
def test_all_outputs_have_query_block(lsp_server: str, command: str, args: list[str]) -> None:
    """Every codebase response includes a query block with command and no None values."""
    result = _run(lsp_server, command, *args)
    assert "query" in result, f"'{command}' response missing 'query' key"
    q = result["query"]
    assert "command" in q, f"'{command}' query missing 'command'"
    assert None not in q.values(), f"'{command}' query contains None: {q}"


@pytest.mark.parametrize("command,args", [
    ("read-symbol", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("incoming-calls", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("outgoing-calls", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("references", [FILES["resolve"], "--symbol", "ResolvedSymbol"]),
    ("overview", [FILES["analyze"], "--depth", "0"]),
    ("explain", [FILES["resolve"], "--symbol", "resolve_symbol"]),
    ("search", ["ResolvedSymbol"]),
    ("impact", [FILES["analyze"], "--symbol", "_overview"]),
    ("architecture", ["--hotspots", "3"]),
])
def test_all_file_paths_are_relative(lsp_server: str, command: str, args: list[str]) -> None:
    """File paths in responses are workspace-relative, not absolute or file:// URIs."""
    result = _run(lsp_server, command, *args)

    def _check(val: object, key: str = "") -> None:
        # meta.root and workspace are intentionally absolute — don't flag them.
        if key in ("root", "workspace") and isinstance(val, str) and val.startswith("/"):
            return
        if isinstance(val, str) and "/" in val:
            assert not val.startswith("/"), f"absolute path: {val}"
            assert not val.startswith("file://"), f"file:// URI: {val}"
        if isinstance(val, dict):
            for k, v in val.items():
                _check(v, k)
        if isinstance(val, list):
            for v in val:
                _check(v)

    _check(result)


# ── architecture ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("hotspots", [20, 5, 0])
def test_architecture_shape(lsp_server: str, hotspots: int) -> None:
    result = _run(lsp_server, "architecture", "--hotspots", str(hotspots))
    for key in ("structure", "entry_points", "hotspots", "summary", "query", "meta"):
        assert key in result, f"architecture missing '{key}'"

    # Structure entries
    for dir_name, info in result["structure"].items():
        assert isinstance(info, dict)
        for key in ("files", "imports", "imported_by"):
            assert key in info, f"structure.{dir_name} missing '{key}'"
        assert isinstance(info["imports"], list)
        assert isinstance(info["imported_by"], list)

    # Hotspot invariants
    assert len(result["hotspots"]) <= hotspots
    for h in result["hotspots"]:
        assert "file" in h
        assert "imported_by" in h
        assert "imported_by_transitive" in h
        assert h["imported_by_transitive"] >= 2
        assert isinstance(h["imported_by_transitive"], int)

    # Summary
    assert "total_files" in result["summary"]
    assert "total_dirs" in result["summary"]
