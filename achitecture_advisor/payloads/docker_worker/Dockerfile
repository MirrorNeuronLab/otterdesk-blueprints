FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
COPY docker_worker/python_dependencies/ /tmp/python_dependencies/
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt
RUN pip install --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt /tmp/python_dependencies/*.whl
COPY docker_worker/engine/ /opt/mn-graph-engine/
ENV PATH="/opt/mn-graph-engine/bin:${PATH}"
RUN rgx --version
COPY domain/ /app/domain/
COPY agents/ /app/agents/
COPY steps/ /app/steps/
COPY runtime/ /app/runtime/
COPY knowledge/ /app/knowledge/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
