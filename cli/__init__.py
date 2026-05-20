"""AivoCode CLI — command-line interface for AI coding agents.

Subcommands are registered via ``add_subparser()`` in each command module.
Run as ``aivocode <subcommand>`` after ``pip install -e .`` or directly via
``python -m cli <subcommand>``.

To add a new command:
    1. Create ``cli/commands/<name>.py`` with ``add_subparser()`` and ``handle()``.
    2. Import and register it in ``cli/main.py``.
"""
