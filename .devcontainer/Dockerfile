# AivoCode devcontainer — extends OpenCode base image.
# Full development environment: conda, Node.js, LSP servers, crawl4ai,
# and the aivocode CLI client (installed from source for any workspace).
FROM ghcr.io/slamengine/base-images/opencode-cpu:latest

# Copy setup scripts and environment definition.
COPY environment.yml setup.sh /tmp/setup/

# Unified setup — same as Dockerfile.prod uses.
RUN bash /tmp/setup/setup.sh

# Install aivocode CLI client into an isolated venv.
# Cloned from the canonical repo — works regardless of what workspace is mounted.
# Uses micromamba run because the system python3 lacks python3-venv/ensurepip.
RUN git clone https://github.com/juldaani/AivoCode /tmp/aivocode && \
    micromamba run -n env-aivocode bash /tmp/aivocode/cli/install.sh --venv /opt/aivocode-cli && \
    rm -rf /tmp/aivocode
