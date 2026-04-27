"""Intentionally broken code for diagnostic tests.

Each error is tagged with its expected diagnostic category.
Tests use this file to verify that the LSP server reports errors.
"""

x: int = "not an int"  # type-error: str is not int

y = undefined_name  # name-error: undefined_name is not defined

z: str = 42  # type-error: int is not str


def bad_func(a: int) -> str:
    """Return type says str but returns int."""
    return a + 1  # type-error: int is not str


def calls_wrong():
    """Pass wrong argument type to bad_func."""
    bad_func("not an int")  # type-error: str is not int
