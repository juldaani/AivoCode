"""Language-agnostic import graph — handler protocol and types.

Why this exists
- Different languages parse imports differently (Python dotted paths vs
  TypeScript ``./relative`` paths vs Rust ``use`` statements).  The
  ``LanguageHandler`` protocol defines a common interface so the
  ``ImportGraph`` can work with any language without knowing the details.

How to add a new language
    1. Implement ``LanguageHandler`` for the language.
    2. Register it in ``_lang_handlers/__init__.py``.
    3. Install the corresponding ``tree-sitter-<lang>`` grammar package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


# ── Import data types ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RawImport:
    """A single import statement extracted from a source file.

    All fields are populated by the language handler's ``extract_imports``
    method.  The ``module`` field is the raw import target as written in
    source code (e.g. ``"os"``, ``"pkg.module"``, ``".sibling"``).

    Attributes
    ----------
    statement : str
        The full import statement text as it appears in the source file.
    module : str
        The module or package being imported (e.g. ``"os"``,
        ``"pkg.module"``, ``".sibling"``, ``"__future__"``).
    names : list[str] or None
        The names being imported from the module.  ``None`` for plain
        ``import X`` statements; a list of strings for
        ``from X import a, b, c``.
    line : int
        1-indexed line number where the import statement starts.
    is_relative : bool
        ``True`` when *module* starts with ``.`` (a relative import).
    lazy : bool
        ``True`` when the import is nested inside a function or class body
        rather than at module scope.
    """

    statement: str
    module: str
    names: list[str] | None
    line: int
    is_relative: bool = False
    lazy: bool = False


# ── Language handler protocol ──────────────────────────────────────────────────


@runtime_checkable
class LanguageHandler(Protocol):
    """Interface for language-specific import extraction and resolution.

    Each language (Python, TypeScript, Rust, ...) implements this protocol
    so the import graph can parse imports, resolve them to file paths, and
    identify test files without knowing language-specific details.

    Implementations must provide:
    - ``suffixes`` — file extensions this handler applies to
    - ``language_name`` — maps to a key in ``_LANGUAGE_GRAMMAR``
    - ``extract_imports`` — tree-sitter-based import parsing
    - ``resolve_import`` — import string → file path resolution
    - ``is_test_file`` — test-file naming convention check
    - ``is_source_file`` — source-file inclusion check
    - ``module_path`` — file path → canonical module identifier
    """

    # ── Class-level configuration ──────────────────────────────────────────

    @property
    def suffixes(self) -> tuple[str, ...]:
        """File extensions this handler applies to (e.g. ``(".py", ".pyi")``)."""
        ...

    @property
    def language_name(self) -> str:
        """Tree-sitter language key (e.g. ``"python"``, ``"typescript"``)."""
        ...

    # ── Import extraction ──────────────────────────────────────────────────

    def extract_imports(self, file_path: Path) -> list[RawImport]:
        """Parse *file_path* with tree-sitter and return all import statements.

        Returns an empty list when the file cannot be read or the language
        grammar is not available.
        """
        ...

    # ── Import resolution ──────────────────────────────────────────────────

    def resolve_import(
        self,
        raw: RawImport,
        from_file: Path,
        file_index: dict[str, Path],
    ) -> Path | None:
        """Resolve a ``RawImport`` to a workspace file path.

        Parameters
        ----------
        raw : RawImport
            The import to resolve (from ``extract_imports``).
        from_file : Path
            Absolute path to the file containing the import.
        file_index : dict[str, Path]
            Mapping from canonical module paths (as returned by
            ``module_path``) to absolute file paths.

        Returns
        -------
        Path or None
            The resolved absolute file path, or ``None`` for external
            imports (stdlib, third-party packages) that are not in the
            workspace.
        """
        ...

    # ── File classification ────────────────────────────────────────────────

    def is_test_file(self, path: str | Path) -> bool:
        """Return ``True`` if *path* matches test-file naming conventions."""
        ...

    def is_source_file(self, path: str | Path) -> bool:
        """Return ``True`` if *path* should be included in the import graph."""
        ...

    # ── Module path computation ─────────────────────────────────────────────

    def module_path(self, file_path: Path, workspace: Path) -> str | None:
        """Compute the canonical module identifier for a file.

        This is the key used in ``file_index`` for import resolution.

        Returns ``None`` when *file_path* cannot be mapped to a module
        (e.g. a standalone script outside any package).

        Python example:
            file:  ``/ws/mock_pkg/utils.py``  → ``"mock_pkg.utils"``
            file:  ``/ws/mock_pkg/__init__.py`` → ``"mock_pkg"``
            file:  ``/ws/standalone.py``       → ``None``
        """
        ...
