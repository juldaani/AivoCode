"""Shared types for testing definition, type_definition, hover, and call_hierarchy.

This module defines classes and functions that are imported by utils.py,
enabling cross-file LSP tests (definition jumps, type resolution, references).

Note: class names use the "Type" prefix to avoid collisions with utils.py's
own Greeter/GreeterFactory (which test different things).
"""

from __future__ import annotations


class TypeGreeter:  ## MARK:class_def
    """Base greeter that produces greeting strings.

    Attributes
    ----------
    name : str
        The name to greet.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self) -> str:  ## MARK:greet_def
        """Return a greeting for this greeter's name."""
        return f"Hello, {self.name}!"


class TypeGreeterFactory:
    """Factory for creating TypeGreeter instances."""

    @staticmethod
    def create(name: str) -> TypeGreeter:
        """Create a TypeGreeter.

        Parameters
        ----------
        name : str
            Name for the greeter.
        """
        return TypeGreeter(name)


def process_greeting(name: str) -> str:
    """Create a greeter and return the formatted greeting.

    Calls TypeGreeterFactory.create and TypeGreeter.greet — useful for
    testing call_hierarchy across function boundaries.
    """
    greeter = TypeGreeterFactory.create(name)
    return greeter.greet()
