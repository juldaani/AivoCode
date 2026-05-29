# AivoCode devcontainer — extends OpenCode base image.
# Full development environment: conda, Node.js, LSP servers, crawl4ai.
FROM ghcr.io/slamengine/base-images/opencode-cpu:latest

# Copy setup scripts and environment definition.
COPY environment.yml setup.sh /tmp/setup/

# Unified setup — same as Dockerfile.prod uses.
RUN bash /tmp/setup/setup.sh
