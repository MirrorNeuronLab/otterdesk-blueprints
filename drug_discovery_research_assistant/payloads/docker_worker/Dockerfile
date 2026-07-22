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
        python3-venv \
        swig \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/mn-venv
ENV PATH="/opt/mn-venv/bin:${PATH}" \
    LD_LIBRARY_PATH="/opt/mn-venv/lib/python3.12/site-packages/torch/lib:${LD_LIBRARY_PATH}"

# mn-python-sdk stages this requirements file from payloads/requirements.txt.
# Keep it before the GNINA build so CMake can use the same CUDA-enabled PyTorch
# runtime that serves DrugClip.
COPY requirements.txt /tmp/mn-skill-runtime/requirements.txt
RUN if [ -s /tmp/mn-skill-runtime/requirements.txt ]; then \
      python3 -m pip install --timeout 120 --retries 10 --break-system-packages --no-cache-dir -r /tmp/mn-skill-runtime/requirements.txt; \
    fi

# GNINA validates its Python test harness while CMake configures the build.
RUN python3 -m pip install --no-cache-dir "pytest>=8,<10"

COPY patches/gnina-cuda-13.patch /tmp/gnina-cuda-13.patch

# GNINA is built natively for the selected CUDA worker; DockerWorker does not
# expose a Docker socket, so Stage D executes this installed binary directly.
# Disable Eigen's host NEON path only in CUDA translation units because NVCC on
# ARM64 cannot parse GCC's arm_neon builtins pulled through GNINA's splines.
RUN export CXXFLAGS="-Wno-error=maybe-uninitialized" TORCH_CUDA_ARCH_LIST="12.1" \
    && git clone --branch "${GNINA_VERSION}" --depth 1 https://github.com/gnina/gnina.git /tmp/gnina \
    && git -C /tmp/gnina apply /tmp/gnina-cuda-13.patch \
    && cmake -S /tmp/gnina -B /tmp/gnina/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES=121 \
        -DCMAKE_CUDA_FLAGS="-DEIGEN_DONT_VECTORIZE" \
        -DCMAKE_PREFIX_PATH="$(python3 -c 'import torch; print(torch.utils.cmake_prefix_path)')" \
    && cmake --build /tmp/gnina/build --parallel 4 \
    && cmake --install /tmp/gnina/build \
    && rm -rf /tmp/gnina

WORKDIR /mn/job/runtime
