FROM bluenviron/mediamtx:1.20.1 AS mediamtx

FROM nvidia/cuda:13.0.0-base-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mediamtx /mediamtx /usr/local/bin/mediamtx
COPY demo/ /opt/cctv-demo/

RUN chmod 0755 /opt/cctv-demo/start_demo_stream.sh \
    && test -s /opt/cctv-demo/sample.mp4 \
    && mediamtx --version

# mirrorneuron: skill-dependencies
# The CLI injects the pinned release dependencies into this build context.
# mirrorneuron: skill-dependencies-end

RUN ffmpeg -hide_banner -hwaccels 2>/dev/null | grep -qx cuda \
    && ffmpeg -hide_banner -filters 2>/dev/null | grep -q scale_cuda \
    && ffmpeg -hide_banner -encoders 2>/dev/null | grep -Eq '(^|[[:space:]])mjpeg([[:space:]]|$)'

WORKDIR /mn/job/visual_detector
ENTRYPOINT []
