"""Test file for import-graph testing — exercises test-file detection.

This file lives in a ``tests/`` directory and its basename starts with
``test_``.  The import graph should identify it as a test file and include
it in ``affected_test_files`` results.

Imports from multiple ``mock_pkg.*`` modules to exercise cross-package
and relative-import test dependencies.
"""

from __future__ import annotations

from pathlib import Path

from mock_pkg.fixtures_classes import GreeterBase, LoudGreeter
from mock_pkg.fixtures_functions import build_tree, leaf_helper
from mock_pkg.fixtures_relative import relative_greet
from mock_pkg.subpkg.deep_relative import deep_greet


# ── Test functions ──────────────────────────────────────────────────────────────


def test_greeter_base_greets_correctly() -> None:
    """Test that uses ``GreeterBase`` from fixtures_classes."""
    g = GreeterBase()
    result = g.greet("world")
    assert result == "Hello, world"


def test_loud_greeter_shouts() -> None:
    """Test that uses ``LoudGreeter`` from fixtures_classes."""
    g = LoudGreeter.make_default()
    result = g.greet("test")
    assert "HELLO" in result


def test_leaf_helper_trims_whitespace() -> None:
    """Test that calls ``leaf_helper`` from fixtures_functions."""
    result = leaf_helper("  TEST  ")
    assert result == "test"


def test_relative_import_symbol_works() -> None:
    """Test that calls a function from fixtures_relative (relative imports)."""
    result = relative_greet("user")
    assert isinstance(result, str)


def test_deep_relative_import_works() -> None:
    """Test that calls a function from subpkg.deep_relative (dot-dot imports)."""
    result = deep_greet("test", workspace=Path("/tmp"))
    assert "deep" in result
