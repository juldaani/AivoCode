"""AivoCode CLI — HTTP client for the aivocode REST API.

Subcommands are registered via ``add_subparser()`` in each command module.
Run as ``python -m cli <subcommand>`` from the repo root.  The CLI sends
HTTP requests to the REST API server at ``$AIVOCODE_URL`` (default
``http://aivocode:8000`` — the compose service name; override for local dev).

To add a new command:
    1. Create ``cli/commands/<name>.py`` with ``add_subparser()`` and ``handle()``.
    2. Import and register it in ``cli/main.py``.
"""
