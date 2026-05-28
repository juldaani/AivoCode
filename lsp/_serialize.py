"""Serialization: LSP DocumentSymbol tree → JSON‑ready dict + output formatter.

What this module provides
- _symbol_tree_to_dict: recursively convert LSP DocumentSymbol objects to
  plain dicts with human-readable kind names.
- result_to_output_json: wrap a query result dict into a JSON string for
  CLI/MCP output. Strips None‑valued keys (matching the web_ops pattern).

Why this exists
- The LSP protocol returns attrs/dataclass objects with nested children.
  All external interfaces (CLI, MCP, REST) need a JSON‑serializable
  representation. This module handles the conversion once, at the library
  level, so endpoints don't duplicate serialization logic.

How to use
    from lsp._serialize import result_to_output_json

    result = await query_document_symbols(my_file)
    print(result_to_output_json(result))

See Also
- lsp._symbols: SYMBOL_KIND_NAMES mapping used for kind→name resolution.
- web_ops.fetcher.result_to_output_json: same pattern (dict → json.dumps,
  strip None keys).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from lsp._symbols import SYMBOL_KIND_NAMES


def _symbol_to_dict(sym: object) -> dict:
    """Convert a single LSP DocumentSymbol (or SymbolInformation) to a plain dict.

    Handles the attrs/dataclass objects returned by the ``lsp-client``
    library. Uses getattr for all field access so this works with any
    duck-typed symbol object.

    Parameters
    ----------
    sym : object
        An LSP DocumentSymbol (with ``name``, ``kind``, ``range``,
        ``selection_range``, and optionally ``children``).

    Returns
    -------
    dict
        Keys: name, kind, kind_number, range, selection_range, children.
        ``children`` is None when empty/falsy rather than an empty list,
        for cleaner JSON output.
    """
    result: dict = {}

    # Core identity fields.
    name = getattr(sym, "name", None)
    if name is not None:
        result["name"] = name

    # Kind: both the human-readable name and the raw integer.
    # The raw integer is useful for programmatic consumers.
    kind = getattr(sym, "kind", 0)
    result["kind"] = SYMBOL_KIND_NAMES.get(kind, f"Kind({kind})")
    result["kind_number"] = kind

    # Range: where the symbol is declared in the file.
    rng = getattr(sym, "range", None)
    if rng is not None:
        result["range"] = {
            "start": {
                "line": getattr(rng.start, "line", 0),
                "character": getattr(rng.start, "character", 0),
            },
            "end": {
                "line": getattr(rng.end, "line", 0),
                "character": getattr(rng.end, "character", 0),
            },
        }

    # Selection range: what the user selected (often same as range).
    sel = getattr(sym, "selection_range", None)
    if sel is not None:
        result["selection_range"] = {
            "start": {
                "line": getattr(sel.start, "line", 0),
                "character": getattr(sel.start, "character", 0),
            },
            "end": {
                "line": getattr(sel.end, "line", 0),
                "character": getattr(sel.end, "character", 0),
            },
        }

    # Children: recursive. None (not []) when empty — cleaner JSON.
    children = getattr(sym, "children", None)
    if children:
        result["children"] = [_symbol_to_dict(c) for c in children]
    else:
        result["children"] = None

    # detail: optional extra info (e.g. type annotations, signatures).
    detail = getattr(sym, "detail", None)
    if detail:
        result["detail"] = detail

    return result


def _symbol_tree_to_dict(symbols: Sequence[object] | None) -> list[dict]:
    """Convert a list of LSP DocumentSymbols to a list of plain dicts.

    Parameters
    ----------
    symbols : Sequence[object] | None
        Top-level symbols returned by the LSP server. None is treated
        as an empty list (server returned nothing).

    Returns
    -------
    list[dict]
        List of symbol dicts (may be empty).
    """
    if symbols is None:
        return []
    return [_symbol_to_dict(s) for s in symbols]


def result_to_output_json(result: dict) -> str:
    """Serialize a query result dict to a JSON string for CLI/MCP output.

    Strips keys whose value is None (matching the ``web_ops`` pattern).
    Uses ``ensure_ascii=False`` for readable non‑ASCII characters.
    Single‑line output (no indent).

    Parameters
    ----------
    result : dict
        A query result dict with keys such as ``file``, ``workspace``,
        ``language``, ``server``, ``symbols``, and optionally ``error``.

    Returns
    -------
    str
        A single-line JSON string.
    """
    cleaned = {k: v for k, v in result.items() if v is not None}
    return json.dumps(cleaned, ensure_ascii=False)
