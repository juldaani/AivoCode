"""CLI subcommand: lsp — query document symbols from the LSP daemon.

Thin UI layer: parses CLI arguments, calls ``lsp.query_document_symbols`` for
all processing (workspace detection, daemon management, LSP query,
serialization), and prints the result as JSON.  No processing logic lives here.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from lsp import query_document_symbols, result_to_output_json


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``lsp`` command on the given subparser group."""
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "lsp",
        help="Query LSP symbols for a file.",
        description=(
            "Query document symbols from the LSP daemon for a source file "
            "and output the result as JSON. The file path is relative to the "
            "git repo root (auto-detected via git rev-parse)."
        ),
    )
    parser.add_argument(
        "file",
        type=str,
        help=(
            "File path relative to the git repo root "
            "(e.g. mock_pkg/utils.py)."
        ),
    )
    parser.add_argument(
        "--symbols",
        action="store_true",
        default=False,
        help="Request document symbols for the file.",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Git repo root. Auto-detected via ``git rev-parse --show-toplevel`` "
            "if not provided."
        ),
    )
    parser.set_defaults(func=handle)


def handle(args: argparse.Namespace) -> int:
    """Execute the lsp command and return an exit code."""

    # ── Resolve workspace if explicitly provided ───────────────────────
    workspace: Path | None = None
    if args.workspace:
        workspace = Path(args.workspace)

    # ── All processing delegated to lsp library ────────────────────────
    result = asyncio.run(
        query_document_symbols(
            Path(args.file),
            workspace=workspace,
        )
    )

    print(result_to_output_json(result), flush=True)

    return 0 if result.get("error") is None else 1
