"""Minimal symbols for deterministic LSP tests."""

from enum import Enum
from typing import Final

MAX_RETRIES: Final[int] = 3
WELCOME_MESSAGE: Final[str] = "hello"
DEFAULT_NAME: Final[str] = "world"
DEFAULT_SEPARATOR: Final[str] = ", "


def hello(name: str) -> str:
    return f"{WELCOME_MESSAGE} {name}"


def goodbye(name: str) -> str:
    return f"goodbye {name}"


def hello_default() -> str:
    return hello(DEFAULT_NAME)


def hello_many(names: list[str]) -> str:
    return ", ".join(hello(name) for name in names)


def format_message(message: str, *, sep: str = DEFAULT_SEPARATOR) -> str:
    return sep.join([WELCOME_MESSAGE, message])


def build_payload(name: str) -> dict[str, object]:
    var1: dict[str, str] = {"name": name}
    var2: float = float(MAX_RETRIES) / 2.0
    var3: list[str] = [WELCOME_MESSAGE, name]
    message: str = " ".join(var3)
    var1["message"] = message
    return {"data": var1, "ratio": var2}


class Greeter:
    def greet(self, name: str) -> str:
        return hello(name)


class LoudGreeter(Greeter):
    def greet(self, name: str) -> str:
        return hello(name).upper()


class GreeterFactory:
    @staticmethod
    def make(prefix: str) -> Greeter:
        greeter = Greeter()
        greeter.greet(prefix)
        return greeter


class GreetingStyle(Enum):
    FRIENDLY = "friendly"
    FORMAL = "formal"
