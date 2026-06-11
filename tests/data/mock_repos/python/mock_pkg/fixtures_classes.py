"""Stable fixture: classes with decorators, inheritance, static/class methods.

Exercises:
- ``@dataclass`` signature extraction (includes decorator in signature)
- Exception class inheritance (class → children with __init__)
- ``@staticmethod`` / ``@classmethod`` decorators
- Multi-level inheritance (GreeterBase → LoudGreeter → ExtraLoudGreeter)
- Enum with methods (overview shows Enum kind)
- children with __init__ (AmbiguousSymbolError has __init__ → children list)
- children: null for dataclass (fields are Variable kind → filtered)
- children: null for LookupErrorBase (inherits __init__ from Exception, no own methods)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ── Exception hierarchy ───────────────────────────────────────────────────────


class LookupErrorBase(Exception):
    """Base for symbol lookup errors.  No own methods — children: null."""
    pass


class SymbolNotFoundError(LookupErrorBase):
    """Raised when a symbol name is not found in the target file."""
    pass


class AmbiguousSymbolError(LookupErrorBase):
    """Raised when a symbol name matches multiple candidates.

    Has an explicit __init__ — children should include it.
    """

    def __init__(self, name: str, candidates: list[str]) -> None:
        self.name = name
        self.candidates = candidates
        super().__init__(f"Ambiguous symbol '{name}': {len(candidates)} matches")


# ── Dataclass (fields → Variable kind, filtered from overview children) ────────


@dataclass(frozen=True, slots=True)
class ResolvedSymbol:
    """A resolved symbol with file position.

    Fields are Variable kind — filtered from overview, so children: null.
    """

    name: str
    kind: str
    line: int
    character: int = 1
    range_start: tuple[int, int] = field(default=(1, 1))
    range_end: tuple[int, int] = field(default=(1, 1))


# ── Class hierarchy with static/class methods ──────────────────────────────────


class GreeterBase:
    """Base class for greeters — referenced from fixtures_callchain.py."""

    def greet(self, name: str) -> str:
        """Return a polite greeting."""
        return f"Hello, {name}"

    def formal_greet(self, name: str) -> str:
        """Return a formal greeting."""
        return f"Dear {name}, greetings."


class LoudGreeter(GreeterBase):
    """Loud greeter — overrides greet, adds factory methods."""

    def greet(self, name: str) -> str:
        """Override: shout the greeting."""
        return super().greet(name).upper()

    @staticmethod
    def make_default() -> "LoudGreeter":
        """Static factory — creates a default instance."""
        return LoudGreeter()

    @classmethod
    def make_named(cls, prefix: str) -> "LoudGreeter":
        """Classmethod factory — creates with a config prefix."""
        instance = cls()
        instance._prefix = prefix
        return instance

    def shout(self, text: str) -> str:
        """Extra method for call hierarchy depth."""
        return text.upper() + "!!!"


class ExtraLoudGreeter(LoudGreeter):
    """Even louder — three levels of inheritance."""

    def greet(self, name: str) -> str:
        return super().greet(name) + "!!!"

    def extra_shout(self, name: str) -> str:
        return self.greet(name) + self.shout("extra")


class GreeterFactory:
    """Factory that creates and caches greeters.

    Uses instance methods — tests outgoing-calls from factory methods.
    """

    def __init__(self):
        self._cache: dict[str, LoudGreeter] = {}

    def create(self, name: str) -> LoudGreeter:
        greeter = LoudGreeter.make_default()
        self._cache[name] = greeter
        return greeter

    def get_cached(self, name: str) -> LoudGreeter | None:
        return self._cache.get(name)


# ── Enum with methods ─────────────────────────────────────────────────────────


class SymbolKind(str, Enum):
    """Symbol kinds from LSP protocol — overview includes Enum kind."""

    FILE = "File"
    MODULE = "Module"
    NAMESPACE = "Namespace"
    CLASS = "Class"
    METHOD = "Method"
    FUNCTION = "Function"

    def is_callable(self) -> bool:
        """Method on an enum — should show as child."""
        return self in (SymbolKind.CLASS, SymbolKind.METHOD, SymbolKind.FUNCTION)
