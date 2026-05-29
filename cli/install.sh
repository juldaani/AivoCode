#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — Install the aivocode CLI in an isolated venv.
#
# Usage:
#     ./cli/install.sh                   # interactive / one-off
#     ./cli/install.sh --venv /opt/avc   # custom venv path (Dockerfile)
#
# What it does:
#   1. Creates a dedicated Python venv at ~/.aivocode-cli (or --venv PATH).
#   2. Pip-installs the standalone ``aivocode-cli`` package (httpx + CLI).
#   3. Symlinks the ``aivocode`` entry point to ~/.local/bin/.
#
# Isolation guarantee:
#   - httpx and its deps live only in the dedicated venv.
#   - Zero impact on the devcontainer's conda env or system Python.
#   - The ``aivocode`` script automatically uses the venv's Python via
#     its shebang line.
#
# After install:
#     aivocode lsp symbols src/main.py
#     aivocode webfetch https://example.com
#     aivocode websearch "python asyncio"
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Resolve the CLI package directory ────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_SRC="${SCRIPT_DIR}"

# ── Venv path (configurable for Dockerfile automation) ───────────────────────
VENV_DIR="${HOME}/.aivocode-cli"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --venv) VENV_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Use the devcontainer's Python if available, otherwise system python3 ─────
PYTHON_BIN="${CONDA_PREFIX:-}/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
    PYTHON_BIN="$(command -v python3 || command -v python)"
fi

echo "==> Creating venv at ${VENV_DIR} (using ${PYTHON_BIN})"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

echo "==> Installing aivocode-cli from ${CLI_SRC}"
"${VENV_DIR}/bin/pip" install --quiet "${CLI_SRC}"

echo "==> Linking aivocode"

# Try a system PATH directory first (no export needed — "just works").
# In devcontainers we're typically root, so /usr/local/bin is writable.
if [ -w "/usr/local/bin" ]; then
    ln -sf "${VENV_DIR}/bin/aivocode" "/usr/local/bin/aivocode"
    echo "    → /usr/local/bin/aivocode (already on PATH)"
else
    # Fall back to ~/.local/bin and ensure it's on PATH in ~/.bashrc.
    mkdir -p "${HOME}/.local/bin"
    ln -sf "${VENV_DIR}/bin/aivocode" "${HOME}/.local/bin/aivocode"
    echo "    → ${HOME}/.local/bin/aivocode"

    BIN_DIR="${HOME}/.local/bin"
    BASHRC="${HOME}/.bashrc"

    if [ -f "${BASHRC}" ]; then
        if ! grep -qF "${BIN_DIR}" "${BASHRC}" 2>/dev/null; then
            echo "" >> "${BASHRC}"
            echo "# Added by aivocode CLI installer" >> "${BASHRC}"
            echo "export PATH=\"${BIN_DIR}:\${PATH}\"" >> "${BASHRC}"
        fi
    fi

    echo ""
    echo "To use aivocode right now, run:"
    echo ""
    echo "  export PATH=\"${BIN_DIR}:\${PATH}\""
    echo "  aivocode --help"
    echo ""
    echo "(~/.local/bin has also been added to ~/.bashrc — future terminals"
    echo " will pick it up automatically.)"
fi

echo ""
echo "Done."
