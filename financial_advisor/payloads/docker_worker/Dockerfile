FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    w3m \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    -r /tmp/mn-skill-runtime/requirements.txt

WORKDIR /mn/job/runtime
ENTRYPOINT []
