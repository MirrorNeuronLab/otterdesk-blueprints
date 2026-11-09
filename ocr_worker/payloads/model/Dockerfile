# Build context: a payload root containing skills/nvidia_ocr_skill/.
# Separate model service; MirrorNeuron workers keep their own lightweight image.
FROM nvcr.io/nvidia/pytorch:25.09-py3@sha256:f3b4a33fd60d5e0358287bb44d57e91eda45e8f1681fef1bfd6c969371417130
ARG TARGETARCH
ENV HF_HOME=/cache HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 \
    GIT_LFS_SKIP_SMUDGE=1 MAX_JOBS=2
RUN python -c "import sys, platform; assert sys.version_info[:2] == (3, 12); assert platform.machine() in {'x86_64', 'aarch64'}"
RUN python -m pip install --no-cache-dir hatchling editables ninja "setuptools>=77" "setuptools-scm>=8"
RUN git init /opt/nemotron-ocr && \
    git -C /opt/nemotron-ocr remote add origin https://huggingface.co/nvidia/nemotron-ocr-v2 && \
    git -C /opt/nemotron-ocr fetch --depth 1 origin 0e83e83f17943524b90afa6c0fd82ac2bc1a40ca && \
    git -C /opt/nemotron-ocr checkout --detach FETCH_HEAD && \
    BUILD_CPP_EXTENSION=0 ARCH=${TARGETARCH} python -m pip install --no-cache-dir --no-build-isolation /opt/nemotron-ocr/nemotron-ocr
COPY skills/nvidia_ocr_skill/ /opt/nvidia-ocr-skill/
# Private SDK packages are injected by Core for workers; the OCR service uses no SDK.
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MIRRORNEURON_NVIDIA_OCR_SKILL=0.1.0 \
    python -m pip install --no-cache-dir --no-deps /opt/nvidia-ocr-skill && \
    python -m pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "pypdfium2>=4.30,<6" "jsonschema>=4.23,<5"
WORKDIR /app
COPY model/serve.py /app/serve.py
EXPOSE 8000
CMD ["python", "/app/serve.py"]
