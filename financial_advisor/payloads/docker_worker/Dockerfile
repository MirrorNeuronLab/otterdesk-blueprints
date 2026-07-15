FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    w3m \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    -r /tmp/mn-skill-runtime/requirements.txt

WORKDIR /mn/job/runtime
ENTRYPOINT []
