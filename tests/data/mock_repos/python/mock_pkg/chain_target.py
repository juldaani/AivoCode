"""Leaf target for testing transitive dependency chains.

This file is imported by ``chain_middle.py``.
``chain_leaf.py`` imports ``chain_middle`` but does NOT directly import this file,
forming a genuine depth-2 transitive chain.

Used by:
- ``import-dependents chain_target.py --depth 3`` → chain_leaf.py at depth 2
- ``affected-tests chain_target.py --depth 3`` → test_transitive_impact.py at depth 2
"""

from __future__ import annotations


def target_function() -> str:
    """A simple function that transitively-dependent files reach."""
    return "reached!"
