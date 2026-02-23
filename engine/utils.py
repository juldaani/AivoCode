from __future__ import annotations

"""Utility functions for the engine.

What this file provides
- Dynamic loading of Python classes from dotted strings.
"""

import importlib
from typing import Any


def import_from_string(dotted_path: str) -> Any:
    """Import a class or object from a dotted path string.

    Example: "lsp_server.basedpyright.BasedPyrightProvider"
    """
    if "." not in dotted_path:
        raise ValueError(f"Invalid dotted path: {dotted_path}")

    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise AttributeError(
            f"Module '{module_path}' has no attribute '{class_name}'"
        )
