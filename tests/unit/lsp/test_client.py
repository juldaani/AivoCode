"""Unit tests for LspClient.supports() method."""

from __future__ import annotations

from pathlib import Path

import pytest

from lsp import LspClient, LanguageEntry
from lsp_client.utils.types import lsp_type


def _make_entry() -> LanguageEntry:
    """Create a minimal LanguageEntry for testing."""
    return LanguageEntry(
        name="python",
        suffixes=(".py",),
        server="basedpyright-langserver",
        server_args=("--stdio",),
    )


class TestSupports:
    """Test the supports() capability check method."""

    def test_supports_returns_true_for_supported_capability(
        self,
    ) -> None:
        """supports() returns True when server advertises the capability."""
        client = LspClient(lang_entry=_make_entry(), workspace=Path("/tmp"))
        client.server_capabilities = lsp_type.ServerCapabilities(
            definition_provider=True,
        )
        assert client.supports("definition_provider") is True

    def test_supports_returns_false_for_missing_capability(
        self,
    ) -> None:
        """supports() returns False for a capability not in server caps."""
        client = LspClient(lang_entry=_make_entry(), workspace=Path("/tmp"))
        client.server_capabilities = lsp_type.ServerCapabilities(
            definition_provider=True,
        )
        # type_hierarchy_provider is not set
        assert client.supports("type_hierarchy_provider") is False

    def test_supports_returns_false_before_init(
        self,
    ) -> None:
        """supports() returns False when server_capabilities is None."""
        client = LspClient(lang_entry=_make_entry(), workspace=Path("/tmp"))
        assert client.server_capabilities is None
        assert client.supports("definition_provider") is False

    def test_supports_returns_false_for_unknown_capability(
        self,
    ) -> None:
        """supports() returns False for a nonexistent capability field."""
        client = LspClient(lang_entry=_make_entry(), workspace=Path("/tmp"))
        client.server_capabilities = lsp_type.ServerCapabilities(
            definition_provider=True,
        )
        assert client.supports("nonexistent_capability") is False
