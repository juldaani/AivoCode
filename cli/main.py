"""AivoCode CLI entry point.

Primary usage: ``python -m cli <subcommand>`` from the repo root.
Also available as the ``aivocode`` console_scripts entry point when
installed via ``pip install -e .`` (PyPI distribution).

Usage::

    python -m cli lsp symbols <file>
    python -m cli webfetch <url>
    python -m cli websearch <query>

To add a new subcommand:
    1. Create ``cli/commands/<name>.py`` with ``add_subparser()`` and ``handle()``.
    2. Import it below and call ``add_subparser(subparsers)``.
"""

from __future__ import annotations

import argparse
import sys

from cli.commands import codebase
from cli.commands import lsp
from cli.commands import webfetch
from cli.commands import websearch


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, dispatch to subcommand, and return exit code.

    Returns:
        0 on success, 1 on subcommand failure, 2 on invalid input.
    """
    parser = argparse.ArgumentParser(
        prog="aivocode",
        description="AivoCode CLI — codebase intelligence tools for AI agents.",
    )
    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
    )

    # ---- register subcommands -----------------------------------------------
    codebase.add_subparser(subparsers)
    lsp.add_subparser(subparsers)
    webfetch.add_subparser(subparsers)
    websearch.add_subparser(subparsers)
    # Future commands: import and call add_subparser(subparsers) here.

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Dispatch to the subcommand handler (set via set_defaults(func=...)).
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
