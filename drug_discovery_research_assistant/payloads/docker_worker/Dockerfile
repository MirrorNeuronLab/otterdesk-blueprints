FROM nvidia/cuda:13.0.0-cudnn-devel-ubuntu24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GNINA_VERSION=v1.3.2

ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND} \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
        libatlas-base-dev \
        libboost-all-dev \
        libeigen3-dev \
        libgoogle-glog-dev \
        libhdf5-dev \
        libjsoncpp-dev \
        libopenbabel-dev \
        libprotobuf-dev \
        librdkit-dev \
        pkg-config \
        protobuf-compiler \
        python3 \
        python3-dev \
        python3-numpy \
        python3-pip \
        swig \
    && rm -rf /var/lib/apt/lists/*

# mn-python-sdk stages this requirements file from payloads/requirements.txt.
# Keep it before the GNINA build so CMake can use the same CUDA-enabled PyTorch
# runtime that serves DrugClip.
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt
RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install --timeout 120 --retries 10 --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi

# GNINA is built natively for the selected CUDA worker; DockerWorker does not
# expose a Docker socket, so Stage D executes this installed binary directly.
RUN git clone --branch "${GNINA_VERSION}" --depth 1 https://github.com/gnina/gnina.git /tmp/gnina \
    && cmake -S /tmp/gnina -B /tmp/gnina/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES=121 \
    && cmake --build /tmp/gnina/build --parallel 4 \
    && cmake --install /tmp/gnina/build \
    && rm -rf /tmp/gnina

WORKDIR /mn/job/runtime
