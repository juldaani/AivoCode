"""Stable fixture: circular imports — B-imports-A, A-lazy-imports-B.

Exercises:
- Top-level absolute import from ``fixtures_circular_a`` (``.helper_a``)
- Functions that are called by ``fixtures_circular_a`` via lazy import
- The circular pair tests that the import graph handles cycles without
  infinite recursion in BFS traversal
"""

from __future__ import annotations

from .fixtures_circular_a import helper_a


# ── Symbols ─────────────────────────────────────────────────────────────────────


def func_b(name: str) -> str:
    """Called by ``circular_entry`` in fixtures_circular_a (circular partner)."""
    return f"b_{name}_b"


def multiply(base: int, factor: int) -> int:
    """Multiplies using helper_a from the circular partner module.

    This function is called lazily by ``process_value`` in
    fixtures_circular_a.
    """
    doubled = helper_a(base)
    return doubled * factor


def describe(value: str) -> str:
    """Standalone helper — no circular dependency concern."""
    return f"B says: {value}"
