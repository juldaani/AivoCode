"""Test file for transitive ``affected_tests`` chain.

Imports ``chain_middle.py`` — but does NOT directly import ``chain_target.py``.
This creates a depth‑2 affected‑test dependency on ``chain_target``.

Used by:
- ``affected-tests chain_target.py --depth 3`` → this file at depth 2
"""

from __future__ import annotations

from mock_pkg.chain_middle import middle_function


def test_transitive_reach() -> None:
    """Verifies that the transitive import chain works."""
    assert middle_function() == "reached!"
