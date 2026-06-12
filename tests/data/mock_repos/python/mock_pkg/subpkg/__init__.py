"""Subpackage for testing relative dot-dot imports.

Modules in this package use ``from .. import X`` to reach the parent
``mock_pkg`` package — exercising the import resolution required by the
import graph.
"""
