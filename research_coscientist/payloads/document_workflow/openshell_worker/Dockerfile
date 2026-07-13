FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates w3m \
    && rm -rf /var/lib/apt/lists/*

# MirrorNeuron injects the manifest's pinned skill dependencies into this
# image at bundle preparation time.

