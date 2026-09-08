FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY domain/ /app/domain/
COPY agents/ /app/agents/
COPY steps/ /app/steps/
COPY runtime/ /app/runtime/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
