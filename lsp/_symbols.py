"""LSP SymbolKind enum mapping.

What this module provides
- SYMBOL_KIND_NAMES: maps LSP SymbolKind integers to human-readable names.

Why this exists
- The LSP spec defines a fixed SymbolKind enum (values 1-26). Every compliant
  server uses the same numbers. This module provides a lookup table so that
  kind numbers can be translated to names before returning through interfaces
  like MCP.

How to use
    from lsp._symbols import SYMBOL_KIND_NAMES
    kind_name = SYMBOL_KIND_NAMES[symbol.kind]  # e.g. 5 -> "Class"

See Also
- LSP 3.17 spec: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#symbolKind
"""

from __future__ import annotations

SYMBOL_KIND_NAMES: dict[int, str] = {
    1: "File",
    2: "Module",
    3: "Namespace",
    4: "Package",
    5: "Class",
    6: "Method",
    7: "Property",
    8: "Field",
    9: "Constructor",
    10: "Enum",
    11: "Interface",
    12: "Function",
    13: "Variable",
    14: "Constant",
    15: "String",
    16: "Number",
    17: "Boolean",
    18: "Array",
    19: "Object",
    20: "Key",
    21: "Null",
    22: "EnumMember",
    23: "Struct",
    24: "Event",
    25: "Operator",
    26: "TypeParameter",
}
