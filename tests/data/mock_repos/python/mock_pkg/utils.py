"""Minimal symbols for deterministic LSP tests."""

from typing import Final

MAX_RETRIES: Final[int] = 3
WELCOME_MESSAGE: Final[str] = "hello"


def hello(name: str) -> str:
    return f"{WELCOME_MESSAGE} {name}"


class Greeter:
    def greet(self, name: str) -> str:
        return hello(name)
