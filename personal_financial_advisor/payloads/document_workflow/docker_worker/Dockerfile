FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    w3m \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    mirrorneuron-blueprint-support-skill \
    mirrorneuron-llm-ocr-skill \
    mirrorneuron-w3m-browser-skill

WORKDIR /mn/job/document_workflow
ENTRYPOINT []
