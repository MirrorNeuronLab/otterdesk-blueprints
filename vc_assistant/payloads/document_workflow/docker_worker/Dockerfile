FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    w3m \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt

# __mn_skill_dependencies are resolved by scripts/run_blueprint_in_docker_worker.sh.
# Dev runs add local mn-skills source paths; prod runs install the same skills from GAR.
RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install -q --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi

RUN python3 -c 'from mn_context_engine_sdk import MemoryItem, WorkingMemory'

WORKDIR /mn/job/document_workflow
ENTRYPOINT []
