# AivoCode devcontainer using devcontainer-base
# Extends base image, creates mamba environment

FROM ghcr.io/slamengine/devcontainer-base/opencode:latest

# Copy environment file
COPY environment.yml /tmp/environment.yml

# Create mamba environment
RUN mamba env create -f /tmp/environment.yml -y && \
    mamba clean -afy

# Auto-activate env-aivocode in all shells
RUN micromamba shell init -s bash --root-prefix /opt/conda && \
    echo 'micromamba activate env-aivocode' >> /root/.bashrc
