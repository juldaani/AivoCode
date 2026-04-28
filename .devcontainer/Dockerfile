# AivoCode devcontainer using devcontainer-base
# Extends base image, creates mamba environment

FROM ghcr.io/slamengine/base-images/opencode-cpu:latest

# Copy environment file
COPY environment.yml /tmp/environment.yml

# Create mamba environment
RUN mamba env create -f /tmp/environment.yml -y && \
    mamba clean -afy

# Setup crawl4ai and verify installation
RUN micromamba run -n env-aivocode crawl4ai-setup && \
    micromamba run -n env-aivocode crawl4ai-doctor

# Install Node.js (needed for TypeScript LSP server)
# Download and install nvm:
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash
RUN \. "$HOME/.nvm/nvm.sh" && \
    nvm install 24 && \
    node -v && \
    npm -v

# Make node and npm available in all shells (login, non-interactive, SSH)
# nvm only works in interactive bash; symlinks ensure PATH availability
RUN \. "$HOME/.nvm/nvm.sh" && \
    ln -s "$(which node)" /usr/local/bin/node && \
    ln -s "$(which npm)" /usr/local/bin/npm && \
    ln -s "$(which npx)" /usr/local/bin/npx

# Install vtsls TypeScript language server globally
RUN \. "$HOME/.nvm/nvm.sh" && \
    npm install -g @vtsls/language-server && \
    ln -s "$(which vtsls)" /usr/local/bin/vtsls

# Auto-activate env-aivocode in all shells
RUN micromamba shell init -s bash --root-prefix /opt/conda && \
    echo 'micromamba activate env-aivocode' >> /root/.bashrc
