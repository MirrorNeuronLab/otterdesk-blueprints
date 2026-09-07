FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY docker_worker/python_dependencies/ /tmp/python_dependencies/
RUN pip install --no-cache-dir /tmp/python_dependencies/*.whl
COPY docker_worker/engine/ /opt/mn-graph-engine/
RUN install -m 0755 /opt/mn-graph-engine/bin/rgx /usr/local/bin/rgx && rgx --version
COPY domain/ /app/domain/
COPY agents/ /app/agents/
COPY steps/ /app/steps/
COPY runtime/ /app/runtime/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
