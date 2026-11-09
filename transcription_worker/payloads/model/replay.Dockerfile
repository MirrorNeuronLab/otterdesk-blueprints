# Reuse the released NeMo/vLLM environment; enable its bundled CTC middleware.
# Keep the entrypoint in its own layer so builds can reuse both base platforms.
FROM docker.io/homerquan/nvidia-transcribe@sha256:13befda8bf29f69d432e221cdefea3b031b614723f3cb9a4afd0f2415a7f2629
COPY --link serve.py /opt/serve.py
