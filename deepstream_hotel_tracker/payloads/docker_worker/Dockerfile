FROM nvcr.io/nvidia/isaac-sim:6.2.0@sha256:a025b65a7442d56806a1cc3f5eed081caf736c24b72d62dccf68ef66945d8690 AS isaac
FROM nvcr.io/nvidia/deepstream:9.1-triton-sbsa-dgx-spark@sha256:6a25ce5964424a2fc18a67212b08fc3a844734e757e8cc2a989f033e3306b1af

USER root
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video,graphics,display
ENV VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json
ENV ACCEPT_EULA=Y
ENV PRIVACY_CONSENT=N
ENV OMNICLIENT_HUB_EXE=/usr/local/bin/hub

# Restore codec libraries removed from the NVIDIA base image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg python3-venv \
    && apt-get install -y --no-install-recommends --reinstall \
        libflac12 libmp3lame0 libmpg123-0 libvpx9 libx264-164 libx265-199 \
    && rm -rf /var/lib/apt/lists/* \
    && ffprobe -version >/dev/null && ffmpeg -version >/dev/null

WORKDIR /opt/hotel
COPY docker_worker/nvdsinfer_custombboxparser_tao.cpp docker_worker/detector_labels.txt ./
RUN g++ -std=c++11 -O2 -shared -fPIC -I/opt/nvidia/deepstream/deepstream/sources/includes \
        -I/usr/local/cuda/include nvdsinfer_custombboxparser_tao.cpp -o detector_parser.so

RUN curl --fail --location --retry 3 --max-time 600 \
      'https://api.ngc.nvidia.com/v2/models/org/nvidia/team/tao/peoplenet_transformer_v2/deployable_v1.0/files?redirect=true&path=dino_fan_small_astro_delta.onnx' \
      --output peoplenet.onnx \
    && echo '974d6a77b4fde5ad83b18bbabc5e3771220e6ee22224e98cdc0cbf733da06038  peoplenet.onnx' | sha256sum -c -

# Keep the generated dependency layer independent of the base image's DALI path.
ENV PATH="/opt/mn-venv/bin:${PATH}" \
    PYTHONPATH=""
RUN /usr/bin/python3 -m venv /opt/mn-venv \
    && python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)' \
    && python3 -m pip install --no-cache-dir 'paho-mqtt==1.6.1' 'protobuf>=4.21' 'PyYAML>=6,<7'

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-gi gir1.2-gst-rtsp-server-1.0 \
        libvulkan1 libxrandr2 libxcursor1 libxi6 libxinerama1 libxkbcommon0 libxcomposite1 libnss3 libpulse0 libasound2t64 \
    && apt-get install -y --no-install-recommends --reinstall gstreamer1.0-plugins-ugly \
    && rm -rf /var/lib/apt/lists/* \
    && gst-inspect-1.0 x264enc >/dev/null \
    && printf '/usr/lib/python3/dist-packages\n' > /opt/mn-venv/lib/python3.12/site-packages/ubuntu-gi.pth \
    && python3 -m pip install --no-cache-dir 'Pillow>=11,<13'

COPY --from=isaac /isaac-sim /isaac-sim
COPY --from=isaac /usr/local/bin/hub /usr/local/bin/hub
COPY isaac/fetch_vendor_assets.py isaac/assets/vendor_assets.json /opt/hotel/vendor/
RUN python3 /opt/hotel/vendor/fetch_vendor_assets.py /opt/hotel/vendor/vendor_assets.json /opt/hotel/atrium/downloads
COPY isaac/assets/agibot_assets.json /opt/hotel/vendor/
RUN python3 /opt/hotel/vendor/fetch_vendor_assets.py /opt/hotel/vendor/agibot_assets.json /opt/hotel/atrium/downloads
COPY isaac/assets/ /opt/hotel/atrium/

WORKDIR /app
COPY domain/ /app/domain/
CMD ["/opt/mn-venv/bin/python3", "-m", "mn_sdk.step_runtime"]
