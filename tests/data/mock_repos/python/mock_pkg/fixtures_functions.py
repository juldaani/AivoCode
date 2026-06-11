"""Stable fixture: async functions, sync functions, lazy imports.

Exercises:
- ``async def`` with lazy imports (import inside function body)
- Private helper ``_private_helper`` — Function kind → included in overview
- ``_OVERVIEW_KINDS`` frozenset — Variable kind → excluded from overview
- Cross-file calls to fixtures_classes (GreeterBase, ResolvedSymbol, LoudGreeter)
- Empty incoming caller (``leaf_helper`` — never called externally)
- Thin wrapper ``sync_wrapper`` that delegates to another function
- Signature extraction for multi-line parameter lists
"""

from __future__ import annotations

from pathlib import Path

from mock_pkg.fixtures_classes import (
    GreeterBase,
    GreeterFactory,
    LoudGreeter,
    ResolvedSymbol,
)

# ── Constant — Variable kind, excluded from overview ──────────────────────────

_OVERVIEW_KINDS: frozenset[str] = frozenset(
    {
        "Function",
        "Method",
        "Constructor",
        "Class",
        "Interface",
        "Struct",
        "Enum",
        "Event",
    }
)


# ── Private helper (Function kind → included) ──────────────────────────────────


def _private_helper(name: str) -> str:
    """Private helper — kind is Function, so overview includes it.

    Called by build_tree and entry_point in fixtures_callchain.
    """
    return name.strip()


# ── Lazy imports (imports inside function body) ────────────────────────────────


async def resolve_symbol(
    file_path: str,
    symbol_name: str,
    *,
    line: int | None = None,
    workspace: Path | None = None,
) -> ResolvedSymbol:
    """Async function with lazy imports inside.

    The ``from lsp import query_document_symbols`` import is inside the
    function body — tests that lazy imports appear as outgoing calls.
    """
    from pathlib import Path as PathAlias  # lazy import — tests alias

    ws = workspace or PathAlias.cwd()
    # Simulated: in production this calls query_document_symbols.
    return ResolvedSymbol(
        name=symbol_name,
        kind="Class",
        line=line or 1,
    )


async def analyze_overview(
    file_path: str | Path,
    *,
    depth: int = 0,
    workspace: Path | None = None,
) -> dict:
    """Async function calling cross-package symbols and lazy imports.

    Calls GreeterBase.greet (cross-file), LoudGreeter.greet (cross-file),
    and import inside function.
    """
    from pathlib import Path as P  # lazy import

    ws = workspace or P.cwd()
    # Cross-file calls:
    greeter = LoudGreeter.make_default()
    greeter.greet("test_user")
    greeter.shout("hello")

    factory = GreeterFactory()
    factory.create("user")

    return {"file": str(file_path), "depth": depth}


# ── Sync helpers ──────────────────────────────────────────────────────────────


def relativize(file_path: str | Path, workspace: Path) -> str:
    """Convert an absolute path to workspace-relative.

    Called by build_tree, sync_wrapper, and entry_point in fixtures_callchain.
    """
    fp = Path(file_path).resolve()
    try:
        return str(fp.relative_to(workspace))
    except ValueError:
        return str(fp)


def build_tree(
    workspace: Path,
    *,
    suffix: str | None = None,
) -> dict:
    """Build a file tree — calls _private_helper and relativize.

    Called by entry_point in fixtures_callchain (cross-file incoming).
    """
    name = _private_helper("  test_user  ")
    result = relativize(workspace / "test.py", workspace)
    return {"name": name, "path": result, "suffix": suffix}


def sync_wrapper(name: str, workspace: Path) -> str:
    """Thin wrapper that delegates to relativize.

    Tests outgoing-calls resolving to a workspace call.
    """
    return relativize(workspace / f"{name}.py", workspace)


def leaf_helper(text: str) -> str:
    """Leaf function — called by fixtures_callchain, never calls anything else.

    Tests empty outgoing-calls (no further calls inside).
    """
    return text.lower()
