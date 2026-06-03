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

import enum
import json
from collections.abc import Sequence
from typing import Any

import attr

from lsp._symbols import SYMBOL_KIND_NAMES


def _normalize_positions_to_one_indexed(data: Any) -> Any:
    """Recursively convert LSP 0-indexed positions to 1-indexed in-place.

    The LSP protocol uses 0-indexed line/character values internally, but
    all practical consumers (editors, shell tools, agent ``read`` offset)
    expect 1-indexed values.  This function walks the result tree and adds
    1 to every ``line`` and ``character`` integer inside any Position-like
    dict (a dict that has BOTH ``line`` and ``character`` keys whose values
    are ``int``).

    This intentionally does NOT match the metadata ``line``/``character``
    strings that the daemon attaches to positional query results (those are
    ``str``, not ``int``), so they are left untouched.

    Parameters
    ----------
    data : Any
        A dict, list, or primitive — typically the output of
        ``_symbol_tree_to_dict`` or ``_lsp_result_to_json``.

    Returns
    -------
    Any
        A new value with all LSP Position line/character values +1'd.
        Primitives and non-matching dicts are returned as-is.
    """
    if data is None:
        return None
    if isinstance(data, (bool, int, float, str)):
        return data
    if isinstance(data, dict):
        # Detect a Position-like dict: exactly 'line' + 'character', both ints.
        # LSP spec: ``Position = { line: uint, character: uint }``.
        # Metadata line/character in positional results are str, not int,
        # so they are naturally skipped by the isinstance check.
        if "line" in data and "character" in data \
                and isinstance(data.get("line"), int) \
                and isinstance(data.get("character"), int):
            return {
                **data,
                "line": data["line"] + 1,
                "character": data["character"] + 1,
            }
        # Not a Position — recurse into values.
        return {k: _normalize_positions_to_one_indexed(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_normalize_positions_to_one_indexed(x) for x in data]
    # Fallback — shouldn't be reached in normal LSP data.
    return data


def _replace_kind_integers(data: Any) -> Any:
    """Walk the result tree and replace ``kind: int`` with human-readable names.

    The LSP protocol uses integer SymbolKind values (e.g. 12 = Function).
    This function converts them to names (e.g. ``"Function"``) everywhere
    in the output tree so consumers never see raw integers.

    Works on the already-serialized dict/list/primitive tree — post
    ``_lsp_result_to_json`` / ``_symbol_tree_to_dict``.
    """
    if data is None:
        return None
    if isinstance(data, (bool, int, float, str)):
        return data
    if isinstance(data, dict):
        # Replace kind integers with human-readable names.
        return {
            k: (
                SYMBOL_KIND_NAMES.get(v, f"Kind({v})")
                if k == "kind" and isinstance(v, int)
                else _replace_kind_integers(v)
            )
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [_replace_kind_integers(x) for x in data]
    return data


def _lsp_result_to_json(obj: Any) -> Any:
    """Convert any LSP return value to a JSON-safe dict, list, or primitive.

    Handles attrs classes (via ``attr.asdict()``), lists, dicts, enums,
    and primitives.  Used by the daemon to serialize LSP method return
    values before sending over the Unix socket.

    attrs classes in the ``lsprotocol`` / ``lsp-client`` ecosystem use
    ``__slots__`` (not ``__dict__``), so ``vars()`` does not work.  We
    detect attrs classes and use ``attr.asdict()`` for full conversion.

    Parameters
    ----------
    obj : Any
        The return value from an ``LspClient.request_*`` method.

    Returns
    -------
    Any
        A JSON-serializable value (dict, list, str, int, float, bool, None).
    """
    if obj is None:
        return None
    # Primitives — check BEFORE enum because StrEnum IS a str subclass.
    if isinstance(obj, (bool, int, float)):
        return obj
    # StrEnum values are also str, so handle str check before enum.
    if isinstance(obj, str):
        return obj
    # Enum values (IntEnum, StrEnum, regular Enum).
    # Use isinstance(obj, enum.Enum) — NOT hasattr(obj, "value") — because
    # many attrs classes (e.g. MarkupContent) have a field named "value"
    # that would be falsely matched.
    if isinstance(obj, enum.Enum):
        return _lsp_result_to_json(obj.value)
    # attrs classes — use attr.asdict for full recursive conversion.
    # attr.has() detects both slotted and dict-based attrs classes.
    if attr.has(obj):
        raw = attr.asdict(obj)
        # Post-process: enum values inside the dict may need conversion.
        if isinstance(raw, dict):
            return {k: _lsp_result_to_json(v) for k, v in raw.items()}
        return _lsp_result_to_json(raw)
    if isinstance(obj, dict):
        return {k: _lsp_result_to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_lsp_result_to_json(x) for x in obj]
    # Fallback: string representation.
    return str(obj)


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
        Keys: name, kind, range, selection_range, children.
        ``children`` is None when empty/falsy rather than an empty list,
        for cleaner JSON output.
    """
    result: dict = {}

    # Core identity fields.
    name = getattr(sym, "name", None)
    if name is not None:
        result["name"] = name

    # Kind: human-readable name (e.g. "Class", "Method").
    kind = getattr(sym, "kind", 0)
    result["kind"] = SYMBOL_KIND_NAMES.get(kind, f"Kind({kind})")

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
