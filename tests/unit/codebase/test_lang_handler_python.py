"""Unit tests for PythonHandler — import extraction, module path, resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebase._lang_handlers._base import RawImport
from codebase._lang_handlers._python import PythonHandler


@pytest.fixture
def handler() -> PythonHandler:
    return PythonHandler()


# ═══════════════════════════════════════════════════════════════════════════════
# extract_imports
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractImports:
    def test_simple_absolute(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("import os\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == "os"
        assert imports[0].names is None
        assert imports[0].is_relative is False
        assert imports[0].lazy is False

    def test_multi_import_on_one_line(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("import os, sys, json\n")
        imports = handler.extract_imports(f)
        modules = {imp.module for imp in imports}
        assert modules == {"os", "sys", "json"}
        assert len(imports) == 3

    def test_aliased_import(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("import os as operating_system\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == "os"
        assert imports[0].names is None

    def test_from_import_single(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from pathlib import Path\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == "pathlib"
        assert imports[0].names == ["Path"]

    def test_from_import_multi_name(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from pathlib import Path, PurePath\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].names == ["Path", "PurePath"]

    def test_from_import_grouped(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from pathlib import (\n    Path,\n    PurePath,\n)\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == "pathlib"
        assert imports[0].names == ["Path", "PurePath"]

    def test_from_import_aliased_name(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from pathlib import Path as P\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].names == ["Path"]  # original name, not alias

    def test_relative_dot_module(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from . import sibling\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == "."
        assert imports[0].names == ["sibling"]
        assert imports[0].is_relative is True

    def test_relative_dot_named(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from .sibling import foo\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == ".sibling"
        assert imports[0].names == ["foo"]
        assert imports[0].is_relative is True

    def test_relative_dotdot(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from ..parent import X, Y\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == "..parent"
        assert imports[0].names == ["X", "Y"]
        assert imports[0].is_relative is True

    def test_future_import(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("from __future__ import annotations\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].module == "__future__"
        assert imports[0].names == ["annotations"]

    def test_lazy_import_inside_function(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo():\n    import os\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].lazy is True
        assert imports[0].module == "os"

    def test_lazy_import_inside_class(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("class Foo:\n    def method(self):\n        import json\n")
        imports = handler.extract_imports(f)
        assert len(imports) == 1
        assert imports[0].lazy is True

    def test_top_level_not_lazy(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("import os\n\ndef foo():\n    pass\n")
        imports = handler.extract_imports(f)
        assert imports[0].lazy is False

    def test_conditional_import_not_lazy(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("if True:\n    import os\n")
        imports = handler.extract_imports(f)
        assert imports[0].lazy is False  # module-level if, not inside def/class

    def test_file_not_found(self, handler, tmp_path):
        f = tmp_path / "nonexistent.py"
        imports = handler.extract_imports(f)
        assert imports == []

    def test_empty_file(self, handler, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("")
        imports = handler.extract_imports(f)
        assert imports == []


# ═══════════════════════════════════════════════════════════════════════════════
# module_path
# ═══════════════════════════════════════════════════════════════════════════════


class TestModulePath:
    def test_package_file(self, handler, tmp_path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "module.py").write_text("")
        result = handler.module_path(tmp_path / "pkg" / "module.py", tmp_path)
        assert result == "pkg.module"

    def test_subpackage(self, handler, tmp_path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "sub").mkdir()
        (tmp_path / "pkg" / "sub" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "sub" / "nested.py").write_text("")
        result = handler.module_path(tmp_path / "pkg" / "sub" / "nested.py", tmp_path)
        assert result == "pkg.sub.nested"

    def test_deeply_nested(self, handler, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "__init__.py").write_text("")
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "b" / "__init__.py").write_text("")
        (tmp_path / "a" / "b" / "c").mkdir()
        (tmp_path / "a" / "b" / "c" / "__init__.py").write_text("")
        (tmp_path / "a" / "b" / "c" / "d.py").write_text("")
        result = handler.module_path(tmp_path / "a" / "b" / "c" / "d.py", tmp_path)
        assert result == "a.b.c.d"

    def test_init_file(self, handler, tmp_path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        result = handler.module_path(tmp_path / "pkg" / "__init__.py", tmp_path)
        assert result == "pkg"

    def test_init_at_root(self, handler, tmp_path):
        # __init__.py at workspace root — the root itself becomes the package.
        # The module name is the temp directory name.
        (tmp_path / "__init__.py").write_text("")
        result = handler.module_path(tmp_path / "__init__.py", tmp_path)
        # The package name is the temp dir basename (e.g. "test_init_at_root0").
        assert result is not None
        assert "." not in result  # single-level package

    def test_standalone_no_package(self, handler, tmp_path):
        # No __init__.py anywhere → file is a top-level module.
        (tmp_path / "script.py").write_text("")
        result = handler.module_path(tmp_path / "script.py", tmp_path)
        assert result == "script"

    def test_package_root_detection(self, handler, tmp_path):
        # src/ has NO __init__.py — it's just a container directory.
        # The package root is src/ (first dir above package without __init__.py).
        # module_path starts from the package root → "pkg.mod".
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "pkg").mkdir()
        (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
        (tmp_path / "src" / "pkg" / "mod.py").write_text("")
        result = handler.module_path(tmp_path / "src" / "pkg" / "mod.py", tmp_path)
        assert result == "pkg.mod"

    def test_outside_workspace(self, handler, tmp_path):
        f = tmp_path / "pkg" / "mod.py"
        f.parent.mkdir()
        f.write_text("")
        other = tmp_path / "other"
        other.mkdir()
        result = handler.module_path(f, other)
        assert result is None

    def test_pyi_file(self, handler, tmp_path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "types.pyi").write_text("")
        result = handler.module_path(tmp_path / "pkg" / "types.pyi", tmp_path)
        assert result == "pkg.types"


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_import
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveImport:
    def test_absolute_resolves(self, handler, tmp_path):
        index = {"pkg.core": tmp_path / "pkg" / "core.py"}
        raw = RawImport(
            statement="from pkg.core import foo",
            module="pkg.core",
            names=["foo"],
            line=1,
        )
        result = handler.resolve_import(raw, tmp_path / "x.py", index)
        assert result == tmp_path / "pkg" / "core.py"

    def test_absolute_external_stdlib(self, handler, tmp_path):
        index: dict[str, Path] = {}
        raw = RawImport(
            statement="import os", module="os", names=None, line=1
        )
        result = handler.resolve_import(raw, tmp_path / "x.py", index)
        assert result is None

    def test_absolute_external_third_party(self, handler, tmp_path):
        index = {"pkg.core": tmp_path / "pkg" / "core.py"}
        raw = RawImport(
            statement="import numpy",
            module="numpy",
            names=None,
            line=1,
        )
        result = handler.resolve_import(raw, tmp_path / "x.py", index)
        assert result is None

    def test_relative_dot(self, handler, tmp_path):
        # from_file = pkg/sub/module.py  → module_path = "pkg.sub.module"
        # ".sibling" → "pkg.sub.sibling"
        (tmp_path / "pkg" / "sub").mkdir(parents=True)
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "sub" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "sub" / "module.py").write_text("")
        sibling = tmp_path / "pkg" / "sub" / "sibling.py"
        sibling.write_text("")

        index = {"pkg.sub.sibling": sibling}
        raw = RawImport(
            statement="from .sibling import foo",
            module=".sibling",
            names=["foo"],
            line=1,
            is_relative=True,
        )
        result = handler.resolve_import(
            raw, tmp_path / "pkg" / "sub" / "module.py", index
        )
        assert result == sibling

    def test_relative_dotdot(self, handler, tmp_path):
        # from_file = pkg/sub/module.py  → module_path = "pkg.sub.module"
        # "..parent_mod" → "pkg.parent_mod"
        (tmp_path / "pkg" / "sub").mkdir(parents=True)
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "sub" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "sub" / "module.py").write_text("")
        parent_mod = tmp_path / "pkg" / "parent_mod.py"
        parent_mod.write_text("")

        index = {"pkg.parent_mod": parent_mod}
        raw = RawImport(
            statement="from ..parent_mod import X",
            module="..parent_mod",
            names=["X"],
            line=1,
            is_relative=True,
        )
        result = handler.resolve_import(
            raw, tmp_path / "pkg" / "sub" / "module.py", index
        )
        assert result == parent_mod

    def test_relative_beyond_root(self, handler, tmp_path):
        # from_file = pkg/module.py  → module_path = "pkg.module"
        # ".." → goes above "pkg" → None
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "module.py").write_text("")

        raw = RawImport(
            statement="from ... import X",
            module="...",
            names=["X"],
            line=1,
            is_relative=True,
        )
        result = handler.resolve_import(
            raw, tmp_path / "pkg" / "module.py", {}
        )
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# is_test_file
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsTestFile:
    def test_prefix(self, handler):
        assert handler.is_test_file("tests/test_foo.py") is True

    def test_suffix(self, handler):
        assert handler.is_test_file("tests/foo_test.py") is True

    def test_in_tests_dir(self, handler):
        assert handler.is_test_file("tests/subdir/helper.py") is True

    def test_in_test_dir_singular(self, handler):
        assert handler.is_test_file("test/test_foo.py") is True

    def test_not_test_source_file(self, handler):
        assert handler.is_test_file("src/utils.py") is False

    def test_not_test_lib_file(self, handler):
        assert handler.is_test_file("pkg/module.py") is False

    def test_path_object(self, handler):
        assert handler.is_test_file(Path("tests/test_foo.py")) is True


# ═══════════════════════════════════════════════════════════════════════════════
# is_source_file
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsSourceFile:
    def test_py_file(self, handler):
        assert handler.is_source_file("src/module.py") is True

    def test_pyi_file(self, handler):
        assert handler.is_source_file("src/types.pyi") is True

    def test_not_python(self, handler):
        assert handler.is_source_file("script.sh") is False

    def test_test_file_excluded(self, handler):
        assert handler.is_source_file("tests/test_foo.py") is False

    def test_hidden_file(self, handler):
        assert handler.is_source_file(".hidden.py") is False

    def test_pycache_excluded(self, handler):
        assert handler.is_source_file("__pycache__/mod.py") is False

    def test_venv_excluded(self, handler):
        assert handler.is_source_file(".venv/lib/mod.py") is False


# ═══════════════════════════════════════════════════════════════════════════════
# _resolve_relative_module (static method)
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveRelativeModule:
    def test_dot_same_package(self, handler):
        result = handler._resolve_relative_module(".", "pkg.sub.module")
        assert result == "pkg.sub"

    def test_dot_named(self, handler):
        result = handler._resolve_relative_module(".sibling", "pkg.sub.module")
        assert result == "pkg.sub.sibling"

    def test_dotdot(self, handler):
        result = handler._resolve_relative_module("..parent", "pkg.sub.module")
        assert result == "pkg.parent"

    def test_dotdotdot(self, handler):
        result = handler._resolve_relative_module("...", "pkg.sub.module")
        assert result is None  # goes above top-level package

    def test_top_level_module(self, handler):
        result = handler._resolve_relative_module(".foo", "module")
        assert result == "foo"
