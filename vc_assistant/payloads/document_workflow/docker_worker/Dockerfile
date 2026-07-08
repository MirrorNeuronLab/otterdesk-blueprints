FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    w3m \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt
COPY local-requirements.txt /tmp/mn-skill-runtime/local-requirements.txt

# mirrorneuron: skill-dependencies
# DockerWorker prepare copies local dev skill sources here when needed.
# mirrorneuron: skill-dependencies-end
RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install -q --timeout 120 --retries 10 --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi
RUN if [ -s /tmp/mn-skill-runtime/local-requirements.txt ]; then \
      python3 -m pip install -q --timeout 120 --retries 10 --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/local-requirements.txt; \
    fi

RUN python3 -c 'from mn_context_engine_sdk import MemoryItem, WorkingMemory' \
    && python3 -c 'from pymilvus import MilvusClient'

WORKDIR /mn/job/document_workflow
ENTRYPOINT []
