"""Stable fixture: relative dot-dot imports from a subpackage.

Exercises:
- ``from ..fixtures_classes import X`` — relative dot-dot, multi-name
- ``from ..fixtures_functions import X`` — relative dot-dot, single name
- ``from ..fixtures_relative import X`` — relative dot-dot from a sibling module
"""

from __future__ import annotations

from pathlib import Path

# ── Relative dot-dot imports ────────────────────────────────────────────────────

from ..fixtures_classes import GreeterBase, ResolvedSymbol
from ..fixtures_functions import build_tree, leaf_helper
from ..fixtures_relative import relative_greet


# ── Symbols ─────────────────────────────────────────────────────────────────────


def deep_greet(name: str, workspace: Path) -> str:
    """Calls ``GreeterBase`` imported via relative dot-dot from parent pkg."""
    greeter = GreeterBase()
    base = greeter.greet(name)
    rel = str(workspace / name)
    return f"[deep] {base} @ {rel}"


def deep_build_and_clean(workspace: Path, name: str) -> dict:
    """Uses ``build_tree`` and ``leaf_helper`` imported via relative dot-dot."""
    tree = build_tree(workspace, suffix=".py")
    cleaned = leaf_helper(f"  {name}  ")
    return {"tree": tree, "cleaned": cleaned}


def deep_via_relative_mod(name: str) -> str:
    """Calls ``relative_greet`` from ``fixtures_relative`` via dot-dot import."""
    return f"via_relative: {relative_greet(name)}"
