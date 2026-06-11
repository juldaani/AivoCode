"""Stable fixture: complex import patterns.

Exercises:
- Multi-name ``from X import (a, b, c)`` grouped imports
- ``import X as Y`` aliases
- ``import X, Y, Z`` multi-import on one line
- Re-exports via ``__all__``
- Imports from fixtures_classes and fixtures_functions (cross-file refs)
- A wrapper class that re-exports generically
"""

from __future__ import annotations

# ── Aliased imports ───────────────────────────────────────────────────────────

import json as json_lib
import os as os_lib

# ── Multi-import on single line ───────────────────────────────────────────────

import pathlib, sys, textwrap

# ── Grouped from-import with parentheses ──────────────────────────────────────

from pathlib import (
    Path,
    PurePath,
    PurePosixPath,
    PureWindowsPath,
)

# ── Standard from-import ──────────────────────────────────────────────────────

from typing import TYPE_CHECKING

# ── Cross-package imports ─────────────────────────────────────────────────────

from mock_pkg.fixtures_classes import (
    GreeterBase,
    GreeterFactory,
    LoudGreeter,
    ResolvedSymbol,
    SymbolKind,
)
from mock_pkg.fixtures_functions import (
    build_tree,
    leaf_helper,
    relativize,
)

# ── Conditional import ────────────────────────────────────────────────────────

if TYPE_CHECKING:
    from mock_pkg.fixtures_callchain import entry_point

# ── Re-exports ────────────────────────────────────────────────────────────────

__all__ = ["normalize_and_greet", "ImportedGreeter", "ReExportedClass"]


# ── Symbols ───────────────────────────────────────────────────────────────────


def normalize_and_greet(name: str, workspace: pathlib.Path) -> str:
    """Normalize a name and return a greeting.

    Calls leaf_helper (from fixtures_functions) and resolve_symbol-like logic.
    """
    cleaned = leaf_helper(name)  # cross-file call
    rel = relativize(workspace / "test.py", workspace)  # cross-file call
    return f"Greetings {cleaned} from {rel}"


class ImportedGreeter:
    """Wrapper that delegates to GreeterBase and calls build_tree.

    Tests cross-file outgoing calls from a class method.
    """

    def __init__(self, base: GreeterBase):
        self._base = base

    def greet_and_build(self, name: str, ws: pathlib.Path) -> str:
        tree = build_tree(ws, suffix=".py")  # cross-file call
        return self._base.greet(name)

    def create_loud(self) -> LoudGreeter:
        return LoudGreeter.make_default()


class ReExportedClass:
    """A class that exists only to be re-exported via __all__."""
    pass
