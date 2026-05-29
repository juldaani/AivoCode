#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh — Unified environment setup for aivocode (dev + prod).
#
# Called by both .devcontainer/Dockerfile and Dockerfile.prod with identical
# parameters.  No "mode" flags needed — the full environment is the same
# everywhere.  The only difference is context (devcontainer has OpenCode;
# prod starts fastapi directly).
#
# What it does:
#   1. Creates the conda env from environment.yml (env-aivocode).
#   2. Installs crawl4ai browser driver (Chromium).
#   3. Installs Node.js via nvm (node 24).
#   4. Symlinks node / npm / npx to /usr/local/bin.
#   5. Installs vtsls TypeScript language server, symlinks to /usr/local/bin.
#   6. Enables micromamba shell init + auto-activates env-aivocode in bash.
#
# Assumptions:
#   - micromamba is available on PATH (base images provide it).
#   - The script and environment.yml live in the same directory when copied.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/environment.yml"

echo "==== aivocode setup ===="
echo ""

# ── 1. Conda environment ─────────────────────────────────────────────────────
echo "[1/5] Creating conda environment from ${ENV_FILE}"
mamba env create -f "${ENV_FILE}" -y
mamba clean -afy
echo ""

# ── 2. crawl4ai browser driver ──────────────────────────────────────────────
echo "[2/5] Setting up crawl4ai (Chromium browser driver)"
micromamba run -n env-aivocode crawl4ai-setup
micromamba run -n env-aivocode crawl4ai-doctor
echo ""

# ── 3. Node.js via nvm ──────────────────────────────────────────────────────
echo "[3/5] Installing Node.js (nvm → node 24)"
curl -sSo- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash
\. "$HOME/.nvm/nvm.sh"
nvm install 24
node -v
npm -v
echo ""

# ── 4. Symlink node / npm / npx to /usr/local/bin ────────────────────────────
echo "[4/5] Linking node, npm, npx → /usr/local/bin"
\. "$HOME/.nvm/nvm.sh"
ln -sf "$(which node)" /usr/local/bin/node
ln -sf "$(which npm)"  /usr/local/bin/npm
ln -sf "$(which npx)"  /usr/local/bin/npx
echo ""

# ── 5. vtsls TypeScript language server ──────────────────────────────────────
echo "[5/5] Installing vtsls TypeScript language server"
\. "$HOME/.nvm/nvm.sh"
npm install -g @vtsls/language-server
ln -sf "$(which vtsls)" /usr/local/bin/vtsls
echo ""

# ── 6. Shell auto-activate ───────────────────────────────────────────────────
echo "[setup] Enabling micromamba shell init + auto-activate"
micromamba shell init -s bash --root-prefix /opt/conda
echo 'micromamba activate env-aivocode' >> /root/.bashrc

echo ""
echo "==== aivocode setup complete ===="
