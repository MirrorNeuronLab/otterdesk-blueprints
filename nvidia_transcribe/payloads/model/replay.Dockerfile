# Reuse the released NeMo/vLLM environment; enable its bundled CTC middleware.
# Build as homerquan/nvidia-transcribe:0.2.0 on the model node before use.
FROM docker.io/homerquan/nvidia-transcribe@sha256:13befda8bf29f69d432e221cdefea3b031b614723f3cb9a4afd0f2415a7f2629
COPY serve.py /opt/serve.py
