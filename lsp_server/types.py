"""Shared JSON type aliases for LSP payloads.

What this file provides
- Small, centralized aliases for JSON-like dictionaries and values.

Why this exists
- Keeps typing consistent across modules that pass JSON-RPC payloads.
"""

from typing import Any

JsonValue = Any
JsonDict = dict[str, JsonValue]
