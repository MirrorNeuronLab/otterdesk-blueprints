FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt
RUN pip install --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt
COPY domain/ /app/domain/
COPY agents/ /app/agents/
COPY steps/ /app/steps/
COPY runtime/ /app/runtime/
COPY knowledge/ /app/knowledge/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
