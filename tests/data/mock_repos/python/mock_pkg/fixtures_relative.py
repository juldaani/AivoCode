"""Stable fixture: relative imports within the same package.

Exercises:
- ``from .fixtures_classes import X`` — relative dot, multi-name import
- ``from . import fixtures_functions`` — relative dot, module import
- ``from .fixtures_enums import X`` — relative dot, single-name import
- Lazy relative import inside a function body
- Comparison: same source file uses both relative and absolute imports
"""

from __future__ import annotations

# ── Relative dot — named imports ────────────────────────────────────────────────

from .fixtures_classes import GreeterBase, LoudGreeter, SymbolKind

# ── Relative dot — module import ────────────────────────────────────────────────

from . import fixtures_functions

# ── Relative dot — single name ──────────────────────────────────────────────────

from .fixtures_enums import GreetingStyle

# ── Absolute imports for comparison ─────────────────────────────────────────────

from pathlib import Path


# ── Symbols ─────────────────────────────────────────────────────────────────────


def relative_greet(name: str, style: GreetingStyle = GreetingStyle.FRIENDLY) -> str:
    """Greet using symbols imported via relative dot.

    Uses ``LoudGreeter`` (from .fixtures_classes) and ``GreetingStyle``
    (from .fixtures_enums).  Calls ``leaf_helper`` via the module-level
    import of ``fixtures_functions``.
    """
    greeter = LoudGreeter.make_default()
    base = greeter.greet(name)
    if style == GreetingStyle.FRIENDLY:
        prefix = "Hey! "
    elif style == GreetingStyle.FORMAL:
        prefix = "Dear "
    else:
        prefix = ""
    cleaned = fixtures_functions.leaf_helper(name)
    return f"{prefix}{base} (clean: {cleaned})"


def relative_chain(names: list[str], workspace: Path) -> list[str]:
    """Calls symbols from multiple relatively-imported modules.

    Uses ``build_tree`` (via ``fixtures_functions`` module import) and
    ``relativize`` via a lazy import inside the function body.
    """
    from .fixtures_functions import relativize  # lazy relative import

    results: list[str] = []
    for name in names:
        fixtures_functions.build_tree(workspace, suffix=".txt")
        rel = relativize(workspace / f"{name}.py", workspace)
        results.append(f"{name} -> {rel}")
    return results
