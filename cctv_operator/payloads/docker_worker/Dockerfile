FROM nvidia/cuda:13.0.0-base-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# mirrorneuron: skill-dependencies
# The CLI injects the pinned release dependencies into this build context.
# mirrorneuron: skill-dependencies-end

RUN ffmpeg -hide_banner -hwaccels 2>/dev/null | grep -qx cuda \
    && ffmpeg -hide_banner -filters 2>/dev/null | grep -q scale_cuda

WORKDIR /mn/job/visual_detector
ENTRYPOINT []
