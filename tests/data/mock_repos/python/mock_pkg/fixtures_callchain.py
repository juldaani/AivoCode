"""Stable fixture: deep call chains, same-file and cross-file.

Exercises:
- 4-level same-file chain: caller_1 → caller_2 → caller_3 → leaf_helper
- Cross-file chain: chain_a → chain_b → _private_helper (in fixtures_functions)
- Mixed entry_point that calls 4 different modules
- Outgoing-calls with mixed same_file + cross_file + external
- Incoming-calls: caller_1 has incoming from entry_point + downstream functions
- Empty incoming for functions only called once
"""

from __future__ import annotations

from pathlib import Path

from mock_pkg.fixtures_classes import (
    GreeterBase,
    GreeterFactory,
    LoudGreeter,
    ResolvedSymbol,
)
from mock_pkg.fixtures_functions import (
    _private_helper,
    build_tree,
    leaf_helper,
    relativize,
    resolve_symbol,
    sync_wrapper,
)


# ── Deep same-file call chain ──────────────────────────────────────────────────
# entry_point → caller_1 → caller_2 → caller_3 → leaf_helper (cross-file)


def caller_3(text: str) -> str:
    """Bottom of the same-file chain — calls cross-file leaf_helper."""
    return leaf_helper(text)  # cross-file outgoing


def caller_2(text: str) -> str:
    """Middle of chain — calls caller_3."""
    return caller_3(text)


def caller_1(text: str, workspace: Path) -> str:
    """Top of same-file chain — calls caller_2 and relativize."""
    rel = relativize(workspace, workspace)  # cross-file outgoing
    inner = caller_2(text)
    return f"{inner} @ {rel}"


# ── Cross-file chain ───────────────────────────────────────────────────────────
# entry_point → chain_a → chain_b → _private_helper (cross-file)


def chain_b(name: str) -> str:
    """Calls cross-file private helper."""
    return _private_helper(f"  {name}  ")  # cross-file outgoing


def chain_a(name: str) -> str:
    """Calls chain_b (same file)."""
    return chain_b(name.upper())


# ── Entry point (calls everything) ─────────────────────────────────────────────


async def entry_point(
    name: str,
    *,
    file_path: str = "/tmp/test.py",
    workspace: Path | None = None,
) -> dict:
    """Top-level entry that exercises all cross-file dependencies.

    Calls from 4 different modules, plus internal calls, plus lazily
    imported calls — tests outgoing-calls with mixed locality.
    """
    from pathlib import Path as P  # lazy import

    ws = workspace or P("/tmp/workspace")

    # Same-file calls
    chain1_result = caller_1(name, ws)
    chain2_result = chain_a(name)

    # Cross-file calls — fixtures_functions
    tree = build_tree(ws, suffix=".py")
    resolved = await resolve_symbol(file_path, name)
    wrapped = sync_wrapper(name, ws)

    # Cross-file calls — fixtures_classes
    greeter = LoudGreeter.make_default()
    greeting = greeter.greet(name)
    greeter.shout(greeting)

    factory = GreeterFactory()
    factory.create(name)

    return {
        "name": name,
        "chain1": chain1_result,
        "chain2": chain2_result,
        "tree": tree,
        "resolved": resolved,
        "wrapped": wrapped,
        "greeting": greeting,
    }
