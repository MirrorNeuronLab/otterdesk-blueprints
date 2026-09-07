FROM debian:bookworm-slim

# This image is intentionally small: analysis is static and air-gapped, so it
# needs Python but no browser, package manager, or source-execution tooling.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# mn-python-sdk writes these files while staging the DockerWorker context from
# dependencies.json. SDK preparation adds source requirements in development.
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt

# mirrorneuron: skill-dependencies
# DockerWorker preparation injects COPY entries for packaged local skill sources.
# mirrorneuron: skill-dependencies-end
RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install -q --timeout 120 --retries 10 --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi

WORKDIR /mn/job/runtime
ENTRYPOINT []
