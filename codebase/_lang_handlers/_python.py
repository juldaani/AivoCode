"""Python language handler for import-graph analysis.

Uses tree-sitter-python to extract import statements and implements
Python-specific module path computation and import resolution.
"""

from __future__ import annotations

import os
from pathlib import Path

from codebase._lang_handlers._base import LanguageHandler, RawImport
from codebase._treesitter import _get_parser


class PythonHandler:
    """Import extraction and resolution for Python source files.

    Implements the ``LanguageHandler`` protocol for ``.py`` and ``.pyi``
    files using the ``tree-sitter-python`` grammar.
    """

    suffixes: tuple[str, ...] = (".py", ".pyi")
    language_name: str = "python"

    # ── Import extraction ──────────────────────────────────────────────────

    def extract_imports(self, file_path: Path) -> list[RawImport]:
        """Parse *file_path* with tree-sitter and return all import statements."""
        parser = _get_parser("python")
        if parser is None:
            return []

        try:
            source = file_path.read_bytes()
        except OSError:
            return []

        tree = parser.parse(source)
        imports: list[RawImport] = []

        # ── Helpers ────────────────────────────────────────────────────────

        def _text(node: "object") -> str:
            """Decode the source bytes spanned by *node*."""
            return source[node.start_byte : node.end_byte].decode()

        def _is_lazy(node: "object") -> bool:
            """Walk up the AST; True if any ancestor is a function/class body."""
            _BODY_NODES = frozenset(
                {
                    "function_definition",
                    "class_definition",
                    "decorated_definition",
                }
            )
            parent = node.parent
            while parent is not None:
                if parent.type in _BODY_NODES:
                    return True
                parent = parent.parent
            return False

        # ── AST walk ───────────────────────────────────────────────────────

        def _walk(node: "object") -> None:
            node_type = node.type

            if node_type == "import_statement":
                # import os, sys, json as j  → one RawImport per module
                lazy = _is_lazy(node)
                statement = _text(node)
                line = node.start_point[0] + 1
                for child in node.named_children:
                    if child.type == "dotted_name":
                        imports.append(
                            RawImport(
                                statement=statement,
                                module=_text(child),
                                names=None,
                                line=line,
                                is_relative=False,
                                lazy=lazy,
                            )
                        )
                    elif child.type == "aliased_import":
                        mod_node = child.child_by_field_name("name")
                        imports.append(
                            RawImport(
                                statement=statement,
                                module=_text(mod_node) if mod_node else "",
                                names=None,
                                line=line,
                                is_relative=False,
                                lazy=lazy,
                            )
                        )

            elif node_type == "import_from_statement":
                # from [.]module import name1, name2 as alias
                lazy = _is_lazy(node)
                statement = _text(node)
                line = node.start_point[0] + 1

                # ── Module name ────────────────────────────────────────
                module_name = ""
                is_relative = False
                mod_node = node.child_by_field_name("module_name")
                if mod_node is not None:
                    if mod_node.type == "dotted_name":
                        module_name = _text(mod_node)
                    elif mod_node.type == "relative_import":
                        is_relative = True
                        for child in mod_node.children:
                            if child.type == "import_prefix":
                                module_name += _text(child)
                            elif child.type == "dotted_name":
                                module_name += _text(child)

                # ── Imported names ─────────────────────────────────────
                # Names appear after the 'import' keyword child.
                names: list[str] = []
                seen_import_kw = False
                for child in node.children:
                    if child.type == "import":
                        seen_import_kw = True
                        continue
                    if not seen_import_kw:
                        continue
                    if child.type == "dotted_name":
                        names.append(_text(child))
                    elif child.type == "aliased_import":
                        alias_name = child.child_by_field_name("name")
                        if alias_name is not None:
                            names.append(_text(alias_name))

                imports.append(
                    RawImport(
                        statement=statement,
                        module=module_name,
                        names=names if names else None,
                        line=line,
                        is_relative=is_relative,
                        lazy=lazy,
                    )
                )

            elif node_type == "future_import_statement":
                # from __future__ import annotations
                lazy = _is_lazy(node)
                statement = _text(node)
                line = node.start_point[0] + 1
                names: list[str] = []
                for child in node.named_children:
                    if child.type == "dotted_name":
                        names.append(_text(child))

                imports.append(
                    RawImport(
                        statement=statement,
                        module="__future__",
                        names=names if names else None,
                        line=line,
                        is_relative=False,
                        lazy=lazy,
                    )
                )

            # Recurse into children (catches lazy imports inside def/class).
            for child in node.children:
                _walk(child)

        _walk(tree.root_node)
        return imports

    # ── Import resolution ──────────────────────────────────────────────────

    def resolve_import(
        self,
        raw: RawImport,
        from_file: Path,
        file_index: dict[str, Path],
    ) -> Path | None:
        """Resolve a ``RawImport`` to a workspace file path.

        For absolute imports (``"pkg.module"``), looks up *raw.module*
        directly in *file_index*.  For relative imports (``".sibling"``),
        resolves against the module path of *from_file*.
        """
        if not raw.is_relative:
            # Absolute import — direct lookup.
            return file_index.get(raw.module)

        # Relative import — resolve against from_file's module path.
        from_module = self.module_path(from_file, workspace=_find_workspace(from_file))
        if from_module is None:
            return None

        resolved = self._resolve_relative_module(raw.module, from_module)
        if resolved is None:
            return None
        return file_index.get(resolved)

    @staticmethod
    def _resolve_relative_module(raw_module: str, from_module_path: str) -> str | None:
        """Resolve a relative import string to an absolute module path.

        Parameters
        ----------
        raw_module : str
            The relative module string from the import statement
            (e.g. ``"."``, ``".sibling"``, ``"..parent.module"``).
        from_module_path : str
            The canonical module path of the file containing the import
            (e.g. ``"pkg.sub.module"``).

        Returns
        -------
        str or None
            Absolute module path, or ``None`` when the relative import
            goes beyond the package root.
        """
        parts = from_module_path.split(".")

        # Count leading dots.
        dots = 0
        rest = raw_module
        while rest.startswith("."):
            dots += 1
            rest = rest[1:]

        if dots > len(parts):
            # Import goes above the package root — cannot resolve.
            return None

        base_parts = parts[:-dots] if dots > 0 else parts

        if rest:
            return ".".join(base_parts + [rest])
        return ".".join(base_parts) if base_parts else None

    # ── File classification ────────────────────────────────────────────────

    def is_test_file(self, path: str | Path) -> bool:
        """Return ``True`` if *path* matches Python test-file conventions.

        A file is considered a test file when:
        - Its basename starts with ``test_`` or ends with ``_test``, OR
        - It lives inside a ``tests/`` or ``test/`` directory.
        """
        p = Path(path)
        name = p.name
        # Basename heuristic.
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        # Directory heuristic.
        norm = str(p).replace("\\", "/")
        parts = norm.split("/")
        for part in parts[:-1]:  # exclude the filename itself
            if part in ("tests", "test"):
                return True
        return False

    def is_source_file(self, path: str | Path) -> bool:
        """Return ``True`` if *path* is a Python source file for the graph.

        Includes ``.py`` and ``.pyi`` files that are not test files,
        not hidden, and not inside a virtual environment or cache directory.
        """
        p = Path(path)
        name = p.name
        # Must have a recognised suffix.
        if p.suffix not in self.suffixes:
            return False
        # Exclude hidden files.
        if name.startswith("."):
            return False
        # Exclude virtual environments and caches.
        norm = str(p).replace("\\", "/")
        for skip_dir in ("__pycache__", ".venv", "venv", ".tox", ".eggs", "node_modules"):
            if f"/{skip_dir}/" in f"/{norm}/":
                return False
        # Exclude test files (they're handled separately).
        if self.is_test_file(p):
            return False
        return True

    # ── Module path computation ─────────────────────────────────────────────

    def module_path(self, file_path: Path, workspace: Path) -> str | None:
        """Compute the canonical Python module identifier for *file_path*.

        Walks up from *file_path* to find the first ancestor directory
        that does **not** contain an ``__init__.py`` — that ancestor is
        the *package root*.  The module path is the relative path from
        the package root to the file, with ``/`` replaced by ``.`` and
        the ``.py`` suffix stripped.

        ``__init__.py`` files map to the package name (the directory
        component).

        Returns ``None`` when *file_path* does not reside under
        *workspace*.
        """
        try:
            abs_path = file_path.resolve()
            ws = workspace.resolve()
            abs_path.relative_to(ws)  # raises ValueError if outside workspace
        except (ValueError, OSError):
            return None

        # Find package root — walk up while each directory has __init__.py.
        current = abs_path.parent
        package_root = current
        while True:
            if not (current / "__init__.py").is_file():
                package_root = current
                break
            if current.parent == current:
                # Reached filesystem root.
                package_root = current
                break
            current = current.parent

        # Compute relative path from package root.
        try:
            rel = abs_path.relative_to(package_root)
        except ValueError:
            return None

        parts = list(rel.parts)

        # __init__.py → last part is the package name (the directory).
        if abs_path.name == "__init__.py":
            # The module path is the directory path.
            if not parts or parts == ["__init__.py"]:
                # __init__.py at the package root itself — empty package?
                return None
            parts = parts[:-1]  # strip __init__.py

        # Strip .py / .pyi suffix from the last part.
        if parts and parts[-1].endswith(".pyi"):
            parts[-1] = parts[-1][: -len(".pyi")]
        elif parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][: -len(".py")]

        if not parts:
            return None

        return ".".join(parts)


# ── Internal helpers ───────────────────────────────────────────────────────────


def _find_workspace(file_path: Path) -> Path:
    """Find the workspace (git root) for *file_path*.

    This is a best-effort local helper; the daemon uses the actual
    ``detect_workspace`` from ``lsp``.  Falls back to walking up the
    directory tree when no git root is found (e.g. in test temp dirs).
    """
    try:
        from lsp import detect_workspace

        return detect_workspace(file_path.resolve())
    except Exception:
        pass

    # Fallback: walk up to find .git directory, or settle for the
    # file's parent directory hierarchy.
    current = file_path.resolve().parent
    while current != current.parent:
        if (current / ".git").is_dir():
            return current
        current = current.parent
    return file_path.resolve().parent
