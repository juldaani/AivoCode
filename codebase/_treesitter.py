"""Tree-sitter infrastructure — parser registry and lazy grammar loading.

Why this exists
- Tree-sitter parsers are needed by both ``_read`` (import extraction) and
  ``_lang_handlers`` (language-specific import parsing).  Keeping the
  parser registry here avoids a circular dependency between those modules.

How to use
    from codebase._treesitter import _get_parser, _LANGUAGE_GRAMMAR
    parser = _get_parser("python")
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Parser

# ── Grammar registry ───────────────────────────────────────────────────────────
# Each language maps to (module_name, attr_name, import_node_types).
# Grammars are lazy-loaded on first use so that missing packages
# (e.g. tree-sitter-rust) do not prevent the tools from starting.

_LANGUAGE_GRAMMAR: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "python": (
        "tree_sitter_python",
        "language",
        ("import_statement", "import_from_statement", "future_import_statement"),
    ),
    "typescript": (
        "tree_sitter_typescript",
        "language_typescript",
        ("import_statement",),
    ),
    "javascript": (
        "tree_sitter_typescript",
        "language_typescript",
        ("import_statement",),
    ),
    "tsx": (
        "tree_sitter_typescript",
        "language_tsx",
        ("import_statement",),
    ),
}

_parser_cache: dict[str, "Parser"] = {}


def _get_parser(language: str) -> "Parser | None":
    """Return a cached tree-sitter ``Parser`` for *language*, or ``None``.

    Grammars are imported lazily from ``_LANGUAGE_GRAMMAR`` and cached
    so that each language is loaded at most once per process lifetime.

    Parameters
    ----------
    language : str
        Language identifier (``"python"``, ``"typescript"``, etc.).

    Returns
    -------
    Parser or None
        ``None`` when *language* is not in ``_LANGUAGE_GRAMMAR`` or the
        grammar package is not installed.
    """
    if language in _parser_cache:
        return _parser_cache[language]

    entry = _LANGUAGE_GRAMMAR.get(language)
    if entry is None:
        return None

    module_name, attr_name, _node_types = entry
    try:
        from tree_sitter import Language, Parser

        mod = importlib.import_module(module_name)
        lang_fn = getattr(mod, attr_name)
        ts_lang = Language(lang_fn())
        parser = Parser(ts_lang)
        _parser_cache[language] = parser
        return parser
    except (ImportError, AttributeError) as exc:
        # Grammar package not installed → don't cache the failure,
        # so retrying works if the package is installed later.
        # Log once per language per process.
        logging.getLogger(__name__).warning(
            "tree-sitter grammar for '%s' not available (%s)",
            language,
            exc,
        )
        return None
