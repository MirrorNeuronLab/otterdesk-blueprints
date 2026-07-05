FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt

RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install -q --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi

WORKDIR /mn/job/document_workflow
ENTRYPOINT []
