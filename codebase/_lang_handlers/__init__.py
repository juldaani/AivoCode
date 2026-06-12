"""Language handler registry for import-graph analysis.

Maps file suffixes to ``LanguageHandler`` instances so the import graph
can dispatch to the correct handler without knowing language details.

How to extend
    Import your handler and add it to ``_SUFFIX_REGISTRY``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from codebase._lang_handlers._python import PythonHandler

if TYPE_CHECKING:
    from codebase._lang_handlers._base import LanguageHandler

_SUFFIX_REGISTRY: dict[str, "LanguageHandler"] = {}


def register_handler(handler: "LanguageHandler") -> None:
    """Register a language handler for all suffixes it declares."""
    for suffix in handler.suffixes:
        _SUFFIX_REGISTRY[suffix] = handler


def get_handler(file_path: str | Path) -> "LanguageHandler | None":
    """Return the ``LanguageHandler`` for *file_path*, or ``None``.

    Dispatch is based on file suffix (extension).  When multiple handlers
    match the same suffix, the last one registered wins.
    """
    suffix = Path(file_path).suffix.lower()
    return _SUFFIX_REGISTRY.get(suffix)


def get_handler_by_language(language_name: str) -> "LanguageHandler | None":
    """Return the ``LanguageHandler`` for a language name, or ``None``.

    Matches against each registered handler's ``language_name`` property.
    """
    for handler in _SUFFIX_REGISTRY.values():
        if handler.language_name == language_name:
            return handler
    return None


# ── Register built-in handlers ─────────────────────────────────────────────────

register_handler(PythonHandler())
