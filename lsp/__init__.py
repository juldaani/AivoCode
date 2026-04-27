"""Custom LSP client for aivocode, backed by basedpyright.

What this package provides
- LspClient: a server-agnostic, config-driven LSP client.
- LanguageEntry: dataclass for one language server configuration.
- load_config: reads lsp_config.toml and returns list[LanguageEntry].
- SYMBOL_KIND_NAMES: maps LSP SymbolKind integers to human-readable names.

How to use
- Use as async context manager::

    from lsp import LspClient, LanguageEntry, load_config

    configs = load_config(Path("lsp_config.toml"))
    for entry in configs:
        async with LspClient(lang_entry=entry, workspace=Path.cwd()) as client:
            async with client.open_files(my_file):
                symbols = await client.request_document_symbol_list(my_file)

See Also
- lsp.client for the full module documentation.
- lsp.config for LanguageEntry and load_config.
- lsp._symbols for SYMBOL_KIND_NAMES.
- lsp_client package for the underlying library.
"""

from lsp.client import LspClient
from lsp.config import LanguageEntry, load_config
from lsp._symbols import SYMBOL_KIND_NAMES

__all__ = ["LspClient", "LanguageEntry", "load_config", "SYMBOL_KIND_NAMES"]