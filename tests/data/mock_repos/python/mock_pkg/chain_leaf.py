"""Leaf file in a transitive dependency chain.

Imports ``chain_middle.py`` — but does NOT directly import ``chain_target.py``.
This creates a genuine depth‑2 dependency on ``chain_target``.

Used by:
- ``import-dependents chain_target.py --depth 3`` → chain_leaf.py at depth 2
"""

from __future__ import annotations

from mock_pkg.chain_middle import middle_function


def leaf_function() -> str:
    """Calls through to ``middle_function`` (which calls ``target_function``)."""
    return middle_function()
