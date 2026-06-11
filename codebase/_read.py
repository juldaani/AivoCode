"""Read the full body text of a named symbol.

Why this exists
- Agents need to read the source code of a specific function or class
  without pulling in the entire file.  ``read_symbol`` resolves the name,
  reads the body range, and returns just that text.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Parser

from codebase._resolve import ResolvedSymbol, relativize
from codebase._snippet import read_range


# ── Tree-sitter registry ──────────────────────────────────────────────────────
# Each language maps to (module_name, attr_name, import_node_types).
# Grammars are lazy-loaded on first use so that missing packages
# (e.g. tree-sitter-rust) do not prevent the tools from starting.

_LANGUAGE_GRAMMAR: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "python":     ("tree_sitter_python",     "language",            ("import_statement", "import_from_statement", "future_import_statement")),
    "typescript": ("tree_sitter_typescript", "language_typescript", ("import_statement",)),
    "javascript": ("tree_sitter_typescript", "language_typescript", ("import_statement",)),
    "tsx":        ("tree_sitter_typescript", "language_tsx",        ("import_statement",)),
}

_parser_cache: dict[str, "Parser"] = {}


def _get_parser(language: str) -> "Parser | None":
    """Return a cached tree-sitter ``Parser`` for *language*, or ``None``.

    Grammars are imported lazily from ``_LANGUAGE_GRAMMAR`` and cached
    so that each language is loaded at most once per process lifetime.
    """
    if language in _parser_cache:
        return _parser_cache[language]

    entry = _LANGUAGE_GRAMMAR.get(language)
    if entry is None:
        return None  # unsupported language → graceful fallback

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
        import logging
        logging.getLogger(__name__).warning(
            "tree-sitter grammar for '%s' not available (%s) — imports will be empty",
            language, exc,
        )
        return None


# ── Import extraction ─────────────────────────────────────────────────────────


def _extract_imports(file_path: str | Path, language: str = "python") -> list[dict]:
    """Extract import statements from a source file using tree-sitter.

    Parameters
    ----------
    file_path : str or Path
        Path to the source file.
    language : str
        Language identifier (``"python"``, ``"typescript"``, etc.).
        Unsupported languages return ``[]``.

    Returns
    -------
    list[dict]
        Each entry has ``line`` (1-indexed) and ``statement`` (raw source text).
    """
    parser = _get_parser(language)
    if parser is None:
        return []

    entry = _LANGUAGE_GRAMMAR.get(language)
    if entry is None:
        return []
    _, _, import_node_types = entry

    try:
        source = Path(file_path).read_bytes()
    except OSError:
        return []

    tree = parser.parse(source)
    imports: list[dict] = []

    # Only walk immediate children of the root node (top-level statements).
    # This excludes lazy imports inside function bodies — agents want to see
    # what the module depends on, not implementation details.
    for child in tree.root_node.children:
        if child.type in import_node_types:
            text = source[child.start_byte:child.end_byte].decode()
            line = child.start_point[0] + 1  # 0-indexed → 1-indexed
            imports.append({"line": line, "statement": text})

    return imports


# ── Symbol reader ──────────────────────────────────────────────────────────────


def _read_symbol(
    symbol: ResolvedSymbol,
    file_path: str | Path,
    workspace: Path | None = None,
) -> dict:
    """Read the full body of *symbol* from *file_path*.

    Returns a dict with ``symbol``, ``body``, ``range_line_char``,
    ``file``, and ``imports`` (all import statements in the file).
    """
    body = read_range(file_path, symbol.range_start[0], symbol.range_end[0])
    ws = workspace or Path.cwd()
    return {
        "symbol": symbol.name,
        "kind": symbol.kind,
        "body": body,
        "range_line_char": {
            "start": list(symbol.range_start),
            "end": list(symbol.range_end),
        },
        "file": relativize(file_path, ws),
        "imports": _extract_imports(file_path),
    }
