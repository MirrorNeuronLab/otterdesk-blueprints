FROM ghcr.io/nvidia/openshell-community/sandboxes/base:latest@sha256:aeef1c63f00e2913ea002ccb3aaf925f338b5c5d70e63576f0d95c16a138044e

USER root
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 ca-certificates && rm -rf /var/lib/apt/lists/*
ARG OPENCODE_VERSION=1.18.33
RUN set -eu; \
    case "$(uname -m)" in aarch64|arm64) arch=arm64 ;; x86_64) arch=x64 ;; *) exit 1 ;; esac; \
    curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${arch}.tar.gz" -o /tmp/opencode.tar.gz; \
    tar -xzf /tmp/opencode.tar.gz -C /usr/local/bin opencode; \
    rm /tmp/opencode.tar.gz; \
    mkdir -p /sandbox/job /sandbox/.cache/opencode /sandbox/.local/share /sandbox/.config; \
    curl -fsSL https://models.dev/api.json -o /sandbox/.cache/opencode/models.json; \
    chown -R sandbox:sandbox /sandbox; \
    opencode --version; \
    python3 --version

ENV XDG_CACHE_HOME=/sandbox/.cache \
    XDG_DATA_HOME=/sandbox/.local/share \
    XDG_CONFIG_HOME=/sandbox/.config \
    OPENCODE_DISABLE_MODELS_FETCH=true
USER sandbox
WORKDIR /sandbox/job
