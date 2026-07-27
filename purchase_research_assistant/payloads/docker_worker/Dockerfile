FROM debian:bookworm-slim

# w3m is the lightweight public-research engine used by the purchase workflow.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    w3m \
    && rm -rf /var/lib/apt/lists/*

# mn-python-sdk generates this file from the manifest's pinned skill and agent
# dependencies before the DockerWorker build context is staged.
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt

RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install -q --timeout 120 --retries 10 --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi

WORKDIR /mn/job/runtime
ENTRYPOINT []
