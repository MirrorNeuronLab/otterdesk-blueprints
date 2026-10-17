FROM python:3.12-slim-bookworm
WORKDIR /app
COPY domain/ /app/domain/
COPY agents/ /app/agents/
COPY steps/ /app/steps/
COPY runtime/ /app/runtime/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
