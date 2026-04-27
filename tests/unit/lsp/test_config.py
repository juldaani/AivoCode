"""Unit tests for lsp.config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp.config import LanguageEntry, load_config


class TestLanguageEntry:
    """Test LanguageEntry dataclass."""

    def test_creation(self) -> None:
        """Basic creation with all fields."""
        entry = LanguageEntry(
            name="python",
            suffixes=(".py", ".pyi"),
            server="basedpyright-langserver",
            server_args=("--stdio",),
        )
        assert entry.name == "python"
        assert entry.suffixes == (".py", ".pyi")
        assert entry.server == "basedpyright-langserver"
        assert entry.server_args == ("--stdio",)

    def test_frozen(self) -> None:
        """LanguageEntry is frozen (immutable)."""
        entry = LanguageEntry(
            name="python",
            suffixes=(".py",),
            server="pylsp",
            server_args=(),
        )
        with pytest.raises(AttributeError):
            entry.name = "typescript"  # type: ignore[misc]

    def test_slots(self) -> None:
        """LanguageEntry uses slots (no __dict__)."""
        entry = LanguageEntry(
            name="python",
            suffixes=(".py",),
            server="pylsp",
            server_args=(),
        )
        assert not hasattr(entry, "__dict__")


class TestLoadConfig:
    """Test load_config function."""

    def test_load_single_language(self, tmp_path: Path) -> None:
        """Load config with one language entry."""
        config_path = tmp_path / "lsp_config.toml"
        config_path.write_text(
            '\n'.join([
                '[[language]]',
                'name = "python"',
                'suffixes = [".py", ".pyi"]',
                'server = "basedpyright-langserver"',
                'server_args = ["--stdio"]',
            ])
        )
        configs = load_config(config_path)
        assert len(configs) == 1
        assert configs[0].name == "python"
        assert configs[0].suffixes == (".py", ".pyi")
        assert configs[0].server == "basedpyright-langserver"
        assert configs[0].server_args == ("--stdio",)

    def test_load_multiple_languages(self, tmp_path: Path) -> None:
        """Load config with multiple language entries."""
        config_path = tmp_path / "lsp_config.toml"
        config_path.write_text(
            '\n'.join([
                '[[language]]',
                'name = "python"',
                'suffixes = [".py"]',
                'server = "basedpyright-langserver"',
                'server_args = ["--stdio"]',
                '',
                '[[language]]',
                'name = "typescript"',
                'suffixes = [".ts", ".tsx"]',
                'server = "typescript-language-server"',
                'server_args = ["--stdio"]',
            ])
        )
        configs = load_config(config_path)
        assert len(configs) == 2
        assert configs[0].name == "python"
        assert configs[1].name == "typescript"

    def test_empty_config(self, tmp_path: Path) -> None:
        """Load config with no language entries returns empty list."""
        config_path = tmp_path / "lsp_config.toml"
        config_path.write_text("")
        configs = load_config(config_path)
        assert configs == []

    def test_missing_name_raises(self, tmp_path: Path) -> None:
        """Config entry without 'name' raises ValueError."""
        config_path = tmp_path / "lsp_config.toml"
        config_path.write_text(
            '\n'.join([
                '[[language]]',
                'suffixes = [".py"]',
                'server = "pylsp"',
            ])
        )
        with pytest.raises(ValueError, match="name"):
            load_config(config_path)

    def test_missing_server_raises(self, tmp_path: Path) -> None:
        """Config entry without 'server' raises ValueError."""
        config_path = tmp_path / "lsp_config.toml"
        config_path.write_text(
            '\n'.join([
                '[[language]]',
                'name = "python"',
                'suffixes = [".py"]',
            ])
        )
        with pytest.raises(ValueError, match="server"):
            load_config(config_path)

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Non-existent config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.toml")

    def test_default_server_args(self, tmp_path: Path) -> None:
        """Missing server_args defaults to empty tuple."""
        config_path = tmp_path / "lsp_config.toml"
        config_path.write_text(
            '\n'.join([
                '[[language]]',
                'name = "python"',
                'suffixes = [".py"]',
                'server = "pylsp"',
            ])
        )
        configs = load_config(config_path)
        assert configs[0].server_args == ()

    def test_default_suffixes(self, tmp_path: Path) -> None:
        """Missing suffixes defaults to empty tuple."""
        config_path = tmp_path / "lsp_config.toml"
        config_path.write_text(
            '\n'.join([
                '[[language]]',
                'name = "python"',
                'server = "pylsp"',
            ])
        )
        configs = load_config(config_path)
        assert configs[0].suffixes == ()
