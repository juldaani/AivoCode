"""Middle file in a transitive dependency chain.

Imports ``chain_target.py`` directly.
Imported by ``chain_leaf.py`` and ``tests/test_transitive_impact.py``.
"""

from __future__ import annotations

from mock_pkg.chain_target import target_function


def middle_function() -> str:
    """Calls through to ``target_function``."""
    return target_function()
