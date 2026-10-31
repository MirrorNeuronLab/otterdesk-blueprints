"""Prepare CCTV's declared vision model before admitting camera evidence."""

import os

from mn_sdk.blueprint_support import source_manifest
from mn_sdk.model_access.runtime import ensure_runtime_model


def prepare_scene_model(config):
    env = os.environ
    declared = source_manifest(__file__, env=env)["runtime"]["models"]["vision"]
    settings = ((config.get("llm") or {}).get("configs") or {}).get("vision") or {}
    # The camera service also hosts text conversation. Its MN_LLM_* settings
    # must not select the text model for the independent vision lane.
    model = env.get("MN_VLM_MODEL") or settings.get("model") or declared["model"]
    provider = env.get("MN_VLM_PROVIDER") or settings.get("provider") or declared["provider"]
    backend = env.get("MN_VLM_BACKEND") or settings.get("backend") or declared.get("backend", "auto")
    return ensure_runtime_model("vlm", model, backend=backend, provider=provider,
        api_base=env.get("MN_VLM_API_BASE") or settings.get("api_base") or "auto",
        model_spec=declared["model_spec"], required_capabilities=["image_input"], env=env)


def framewise_scene_model(config):
    declared = source_manifest(__file__, env=os.environ)["runtime"]["models"]["vision"]
    settings = ((config.get("llm") or {}).get("configs") or {}).get("vision") or {}
    model = os.environ.get("MN_VLM_MODEL") or settings.get("model") or declared["model"]
    backend = os.environ.get("MN_VLM_BACKEND") or settings.get("backend") or declared.get("backend")
    provider = os.environ.get("MN_VLM_PROVIDER") or settings.get("provider") or declared["provider"]
    return model == declared["model"] and backend == "vllm" and provider == declared["provider"]
