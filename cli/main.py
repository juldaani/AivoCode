"""AivoCode CLI entry point.

Registered as the ``aivocode`` console_scripts entry point via ``pyproject.toml``.

Usage::

    aivocode webfetch <url> [--wait-until ...]

To add a new subcommand:
    1. Create ``cli/commands/<name>.py`` with ``add_subparser()`` and ``handle()``.
    2. Import it below and call ``add_subparser(subparsers)``.
"""

from __future__ import annotations

import argparse
import sys

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
    webfetch.add_subparser(subparsers)
    websearch.add_subparser(subparsers)
    # Future commands: import and call add_subparser(subparsers) here.

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # Dispatch to the subcommand handler (set via set_defaults(func=...)).
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
