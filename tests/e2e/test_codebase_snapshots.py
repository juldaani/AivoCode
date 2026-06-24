"""End-to-end snapshot tests: ``python -m cli codebase`` golden-file regression.

What this tests
- Runs codebase commands against stable fixture files in
  ``tests/data/mock_repos/python/mock_pkg/``.
- Compares full JSON output against committed snapshot files.
- Catches unintended behavioral changes when refactoring (e.g. ast.parse → tree-sitter).

Fixture files are intentionally stable and never change — only tool code changes.
All cross-file imports/references/calls are documented inside each fixture.

Update snapshots
    pytest tests/e2e/test_codebase_snapshots.py --update-snapshots

Snapshots live in ``tests/e2e/snapshots/``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"

# Stable fixture files — never change, only tool code changes.
_PREFIX = "tests/data/mock_repos/python/mock_pkg"
F_CLASSES = f"{_PREFIX}/fixtures_classes.py"
F_FUNCTIONS = f"{_PREFIX}/fixtures_functions.py"
F_IMPORTS = f"{_PREFIX}/fixtures_imports.py"
F_CALLCHAIN = f"{_PREFIX}/fixtures_callchain.py"
F_ENUMS = f"{_PREFIX}/fixtures_enums.py"


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


# ── Snapshot helper ────────────────────────────────────────────────────────────


_update_mode: bool = False


def _normalize(obj: object) -> object:
    """Return a deterministic version of *obj* with lists sorted.

    LSP results can return lists in non-deterministic order (references,
    symbols, incoming/outgoing calls).  We sort every list by its
    ``json.dumps`` representation so that snapshots are comparable across
    runs without false-positive ordering diffs.

    Also strips ``references_count`` from overview entries — this field
    varies between LSP daemon runs and is validated by schema tests instead.
    """
    if isinstance(obj, dict):
        # Strip non-deterministic fields.
        stripped = {k: v for k, v in obj.items() if k != "references_count"}
        return {k: _normalize(v) for k, v in stripped.items()}
    if isinstance(obj, list):
        # Sort by stable JSON key.
        return sorted((_normalize(v) for v in obj), key=lambda x: json.dumps(x, sort_keys=True))
    return obj


def _assert_snapshot(name: str, data: dict) -> None:
    """Compare *data* against the committed snapshot file *name*.json."""
    normalized = _normalize(data)
    path = _SNAPSHOT_DIR / f"{name}.json"
    if _update_mode or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        return

    expected = json.loads(path.read_text(encoding="utf-8"))
    assert normalized == expected, (
        f"Snapshot mismatch for '{name}'.  Run with --update-snapshots to regenerate."
    )


# ── tree ───────────────────────────────────────────────────────────────────────


def test_snapshot_tree_py(lsp_server: str) -> None:
    result = _run(lsp_server, "tree", "--suffix", ".py")
    _assert_snapshot("tree__suffix_py", result)


# ── search ─────────────────────────────────────────────────────────────────────
# Search results depend on LSP daemon indexing state (workspace-symbol
# may return empty from a cold daemon).  These are tested via schema
# assertions in test_codebase_schema.py instead.


# ── overview ───────────────────────────────────────────────────────────────────


def test_snapshot_overview_classes(lsp_server: str) -> None:
    """Overview of decorator-heavy class file at depth 0."""
    result = _run(lsp_server, "overview", F_CLASSES, "--depth", "0")
    _assert_snapshot("overview__fixtures_classes__depth0", result)


def test_snapshot_overview_functions(lsp_server: str) -> None:
    """Overview of function-heavy file — private included, constants excluded."""
    result = _run(lsp_server, "overview", F_FUNCTIONS, "--depth", "0")
    _assert_snapshot("overview__fixtures_functions__depth0", result)


def test_snapshot_overview_imports(lsp_server: str) -> None:
    """Overview of import-heavy file — tests complex import parsing."""
    result = _run(lsp_server, "overview", F_IMPORTS, "--depth", "0")
    _assert_snapshot("overview__fixtures_imports__depth0", result)


def test_snapshot_overview_callchain(lsp_server: str) -> None:
    """Overview of call-chain file — function-only."""
    result = _run(lsp_server, "overview", F_CALLCHAIN, "--depth", "0")
    _assert_snapshot("overview__fixtures_callchain__depth0", result)


def test_snapshot_overview_enums(lsp_server: str) -> None:
    """Overview of enums + dataclasses + empty classes — children edge cases."""
    result = _run(lsp_server, "overview", F_ENUMS, "--depth", "1")
    _assert_snapshot("overview__fixtures_enums__depth1", result)


# ── read ───────────────────────────────────────────────────────────────────────


def test_snapshot_read_resolve_symbol(lsp_server: str) -> None:
    result = _run(lsp_server, "read-symbol", F_FUNCTIONS, "--symbol", "resolve_symbol")
    _assert_snapshot("read_symbol__resolve_symbol", result)


def test_snapshot_read_ResolvedSymbol(lsp_server: str) -> None:
    result = _run(lsp_server, "read-symbol", F_CLASSES, "--symbol", "ResolvedSymbol")
    _assert_snapshot("read_symbol__ResolvedSymbol", result)


def test_snapshot_read_LoudGreeter(lsp_server: str) -> None:
    result = _run(lsp_server, "read-symbol", F_CLASSES, "--symbol", "LoudGreeter")
    _assert_snapshot("read_symbol__LoudGreeter", result)


# ── incoming-calls ────────────────────────────────────────────────────────────


def test_snapshot_incoming_entry_point(lsp_server: str) -> None:
    result = _run(lsp_server, "incoming-calls", F_CALLCHAIN, "--symbol", "entry_point")
    _assert_snapshot("incoming__entry_point", result)


def test_snapshot_incoming_caller_1(lsp_server: str) -> None:
    result = _run(lsp_server, "incoming-calls", F_CALLCHAIN, "--symbol", "caller_1")
    _assert_snapshot("incoming__caller_1", result)


# ── outgoing-calls ────────────────────────────────────────────────────────────


def test_snapshot_outgoing_entry_point(lsp_server: str) -> None:
    result = _run(lsp_server, "outgoing-calls", F_CALLCHAIN, "--symbol", "entry_point")
    _assert_snapshot("outgoing__entry_point", result)


def test_snapshot_outgoing_resolve_symbol(lsp_server: str) -> None:
    result = _run(lsp_server, "outgoing-calls", F_FUNCTIONS, "--symbol", "resolve_symbol")
    _assert_snapshot("outgoing__resolve_symbol", result)


# ── references ─────────────────────────────────────────────────────────────────


def test_snapshot_references_ResolvedSymbol(lsp_server: str) -> None:
    result = _run(lsp_server, "references", F_CLASSES, "--symbol", "ResolvedSymbol")
    _assert_snapshot("references__ResolvedSymbol", result)


def test_snapshot_references_GreeterBase(lsp_server: str) -> None:
    result = _run(lsp_server, "references", F_CLASSES, "--symbol", "GreeterBase")
    _assert_snapshot("references__GreeterBase", result)


# ── explain ────────────────────────────────────────────────────────────────────


def test_snapshot_explain_entry_point(lsp_server: str) -> None:
    result = _run(lsp_server, "explain", F_CALLCHAIN, "--symbol", "entry_point")
    _assert_snapshot("explain__entry_point", result)


def test_snapshot_explain_ResolvedSymbol(lsp_server: str) -> None:
    result = _run(lsp_server, "explain", F_CLASSES, "--symbol", "ResolvedSymbol")
    _assert_snapshot("explain__ResolvedSymbol", result)


# ── impact ─────────────────────────────────────────────────────────────────────


def test_snapshot_impact_analyze_overview(lsp_server: str) -> None:
    result = _run(lsp_server, "impact", F_FUNCTIONS, "--symbol", "analyze_overview")
    _assert_snapshot("impact__analyze_overview", result)


def test_snapshot_impact_entry_point(lsp_server: str) -> None:
    result = _run(lsp_server, "impact", F_CALLCHAIN, "--symbol", "entry_point")
    _assert_snapshot("impact__entry_point", result)


# ── architecture ────────────────────────────────────────────────────────────────


def test_snapshot_architecture(lsp_server: str) -> None:
    result = _run(lsp_server, "architecture", "--hotspots", "5")
    _assert_snapshot("architecture__hotspots5", result)
