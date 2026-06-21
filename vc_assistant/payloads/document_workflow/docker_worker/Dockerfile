FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    w3m \
    && rm -rf /var/lib/apt/lists/*

COPY build_context/blueprint_support_skill /tmp/mn-skills/blueprint_support_skill
COPY build_context/llm_ocr_skill /tmp/mn-skills/llm_ocr_skill
COPY build_context/rag_skill /tmp/mn-skills/rag_skill
COPY build_context/w3m_browser_skill /tmp/mn-skills/w3m_browser_skill
COPY build_context/web_browser_skill /tmp/mn-skills/web_browser_skill
COPY build_context/mn-python-sdk /tmp/mn-packages/mn-python-sdk
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt

RUN python3 -m pip install -q --break-system-packages --no-cache-dir \
    /tmp/mn-packages/mn-python-sdk \
    /tmp/mn-skills/blueprint_support_skill \
    /tmp/mn-skills/llm_ocr_skill \
    /tmp/mn-skills/rag_skill \
    /tmp/mn-skills/w3m_browser_skill \
    /tmp/mn-skills/web_browser_skill

RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install -q --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi

RUN python3 -c 'from mn_context_engine_sdk import MemoryItem, WorkingMemory'

WORKDIR /mn/job/document_workflow
ENTRYPOINT []
