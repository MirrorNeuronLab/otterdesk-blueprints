# Separate model service: workers use Python 3.12; the upstream serving lock uses 3.13.
FROM nvidia/cuda:13.2.0-devel-ubuntu24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates curl build-essential libsndfile1 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /uvx /usr/local/bin/
RUN git init /opt/nemo && git -C /opt/nemo remote add origin https://github.com/NVIDIA-NeMo/Speech.git && \
    git -C /opt/nemo fetch --depth 1 origin 9b3fc483286e428e93d4426fb08599e89b8d46e3 && \
    git -C /opt/nemo checkout --detach FETCH_HEAD
WORKDIR /opt/nemo
RUN --mount=type=cache,target=/root/.cache/uv uv venv --python 3.13 .venv && \
    UV_PROJECT_ENVIRONMENT=/opt/nemo/.venv uv sync --extra asr --extra vllm --locked --no-install-project && \
    uv pip install --python .venv/bin/python --no-deps -e .
# Ignore the training project's OpenCV exclusion for these explicitly required extras.
RUN --mount=type=cache,target=/root/.cache/uv uv --no-config pip install --python .venv/bin/python --no-deps av==19.0.2 opencv-python-headless==5.0.0.93
# Cross builds check metadata without executing target CUDA/CPU kernels in QEMU.
RUN .venv/bin/python -c "import importlib.metadata as m; assert m.version('vllm') == '0.32.0'; assert m.version('opencv-python-headless') == '5.0.0.93'; assert any(e.name == 'nemo_speechlm' for e in m.entry_points(group='vllm.general_plugins'))"
COPY serve.py /opt/serve.py
ENV PATH=/opt/nemo/.venv/bin:/usr/local/cuda/bin:${PATH} \
    HF_HOME=/cache/huggingface HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 \
    VLLM_PLUGINS=nemo_speechlm VLLM_MAX_AUDIO_DECODE_DURATION_S=3600 \
    VLLM_MAX_AUDIO_CLIP_FILESIZE_MB=180 VLLM_USE_V2_MODEL_RUNNER=0 \
    VLLM_DISABLED_KERNELS=FlashInferFP8ScaledMMLinearKernel
EXPOSE 8000
ENTRYPOINT ["/opt/nemo/.venv/bin/python", "/opt/serve.py"]
