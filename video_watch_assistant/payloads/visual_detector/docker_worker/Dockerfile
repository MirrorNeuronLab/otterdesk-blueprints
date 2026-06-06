FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    python3 \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /mn/job/visual_detector
ENTRYPOINT []
