"""Stable fixture: circular imports — A-lazy-imports-B, B-imports-A.

Exercises:
- Top-level exports used by ``fixtures_circular_b`` via absolute import
- Lazy import of ``fixtures_circular_b`` inside a function body (avoids
  top-level ``ImportError`` caused by the circular dependency)
- Both modules define functions that call each other
"""

from __future__ import annotations

from pathlib import Path


# ── Top-level symbols (safe to import from circular partner) ────────────────────


def helper_a(value: int) -> int:
    """Simple helper — imported by fixtures_circular_b at top level."""
    return value * 2


def describe_kind(kind_name: str) -> str:
    """Return a description for a symbol kind string."""
    return f"Symbol kind: {kind_name}"


# ── Circular call — lazy import avoids top-level ImportError ────────────────────


def circular_entry(name: str) -> str:
    """Entry point that calls into the circular partner B.

    The import of ``func_b`` is lazy so that ``fixtures_circular_b`` can
    safely import ``helper_a`` from this module at top level without
    hitting an uninitialised-module error.
    """
    from .fixtures_circular_b import func_b  # lazy import — circular partner

    return func_b(name) + "_from_A"


def process_value(value: int, *, factor: int = 3) -> int:
    """Combines helper_a with a lazy call into the circular partner."""
    from .fixtures_circular_b import multiply  # lazy import

    base = helper_a(value)
    return multiply(base, factor)
