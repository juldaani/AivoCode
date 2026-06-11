"""Stable fixture: enums, dataclasses, empty classes, constants.

Exercises:
- Enum class → overview includes (Enum kind)
- ``SimpleData`` dataclass with ClassVar → fields filtered, children: null
- ``EmptyContainer`` class with pass only → no methods, children: null
- ``GreetingStyle`` enum with a method → children include method
- Constants at module level → Variable kind, excluded from overview
- ``_PRIVATE_CONST`` → also excluded (Variable kind)
- ``CONFIG_DEFAULTS`` dict → Variable kind, excluded
- ``ProcessedData`` dataclass with regular + ClassVar fields → mixed
- Signature extraction: class with no decorator vs. dataclass with decorator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


# ── Constants (Variable kind — excluded from overview) ────────────────────────


MAX_RETRIES: int = 3
DEFAULT_GREETING: str = "Hello, world!"
_PRIVATE_CONST: frozenset[str] = frozenset({"debug", "trace", "info"})
CONFIG_DEFAULTS: dict[str, object] = {
    "timeout": 5.0,
    "max_depth": 10,
    "verbose": False,
}


# ── Enum with method ──────────────────────────────────────────────────────────


class GreetingStyle(str, Enum):
    """Enum for greeting styles — kind Enum, included in overview."""

    FRIENDLY = "friendly"
    FORMAL = "formal"
    CASUAL = "casual"

    def to_prefix(self) -> str:
        """Method on enum — should appear as child."""
        if self is GreetingStyle.FRIENDLY:
            return "Hey"
        elif self is GreetingStyle.FORMAL:
            return "Dear"
        return "Hi"


# ── Dataclass with ClassVar (children: null — all fields filtered) ────────────


@dataclass
class SimpleData:
    """Dataclass with ClassVar field — all fields are Variable or ClassVar kind.

    Overview should show children: null since no fields are callable kinds.
    """

    name: str
    count: int = 0
    _internal: ClassVar[str] = "default"


# ── Empty class (children: null — no methods) ──────────────────────────────────


class EmptyContainer:
    """A class with no methods, no fields — just documentation.

    Overview should show children: null.
    """
    pass


# ── Mixed dataclass ────────────────────────────────────────────────────────────


@dataclass
class ProcessedData:
    """Dataclass mixing regular fields with ClassVar and default factories.

    Overview: children: null (all fields are Variable/ClassVar kind).
    """

    items: list[str]
    ratio: float = 1.0
    cache_key: ClassVar[str] = "processed_data"
    _id_counter: ClassVar[int] = 0

    def __post_init__(self) -> None:
        """Post-init hook — should appear as child? Depends on LSP."""
        ProcessedData._id_counter += 1

    def summary(self) -> str:
        """Returns a summary string — this IS a Method, should be child."""
        return f"ProcessedData({len(self.items)} items, ratio={self.ratio})"
