FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY domain/ /app/domain/
CMD ["python3", "-m", "mn_sdk.step_runtime"]
