"""Pytest configuration for LSP tests.

What this file provides
- Ensures the repository root is on sys.path for local imports.

Why this exists
- Tests import modules from the repo without installing a package.
"""

from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
