FROM bluenviron/mediamtx:1.20.1 AS mediamtx

FROM nvcr.io/nvidia/pytorch:25.11-py3@sha256:417cbf33f87b5378849df37983552cd1f8bc8b62fe1ceabe004de816a55dff21

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mediamtx /mediamtx /usr/local/bin/mediamtx
COPY docker_worker/demo/ /opt/cctv-demo/

RUN chmod 0755 /opt/cctv-demo/start_demo_stream.sh \
    && mediamtx --version

# mirrorneuron: skill-dependencies
# The CLI injects the pinned release dependencies into this build context.
# mirrorneuron: skill-dependencies-end

COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt
COPY domain/person_detector.py /opt/cctv-models/person_detector.py

# Both comparison checkpoints are SHA-256 pinned and prepared at build.
# Runtime creates the architecture without an automatic model downloader.
RUN python3 -c 'import torch; assert torch.version.cuda, "RF-DETR worker requires a CUDA-enabled PyTorch build"' \
    && python3 /opt/cctv-models/person_detector.py --prepare

RUN ffmpeg -hide_banner -hwaccels 2>/dev/null | grep -qx cuda \
    && ffmpeg -hide_banner -filters 2>/dev/null | grep -q scale_cuda \
    && ffmpeg -hide_banner -encoders 2>/dev/null | grep -Eq '(^|[[:space:]])mjpeg([[:space:]]|$)'

WORKDIR /mn/job/visual_detector
ENTRYPOINT []
