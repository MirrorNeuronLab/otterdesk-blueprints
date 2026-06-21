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
COPY build_context/w3m_browser_skill /tmp/mn-skills/w3m_browser_skill
COPY build_context/mn-python-sdk /tmp/mn-packages/mn-python-sdk

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    /tmp/mn-packages/mn-python-sdk \
    /tmp/mn-skills/blueprint_support_skill \
    /tmp/mn-skills/llm_ocr_skill \
    /tmp/mn-skills/w3m_browser_skill

WORKDIR /mn/job/document_workflow
ENTRYPOINT []
