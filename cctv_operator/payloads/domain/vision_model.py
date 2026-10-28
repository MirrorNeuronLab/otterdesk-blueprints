"""CCTV model policy; the SDK owns transport, durable responses and effect fences."""

import base64
import json
import re

from mn_live_video_analysis_skill import model_user_content
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.model_json import parse_model_json

from .visual_detection import normalize_detection


def prepare(block, frames, prompt):
    declared = source_manifest(__file__, env=block.environment)["runtime"]["models"]["vision"]
    configured = ((block.config.get("llm") or {}).get("configs") or {}).get("vision") or {}
    env = block.environment or {}
    def setting(*names, default=None):
        return next((env[name] for name in names if env.get(name)), default)
    model = setting("MN_VLM_MODEL", "MN_LLM_MODEL", "VL_MODEL_NAME", "OLLAMA_MODEL",
        default=configured.get("model") or declared["model"])
    provider = setting("MN_VLM_PROVIDER", "MN_LLM_PROVIDER", "VL_MODEL_PROVIDER",
        default=configured.get("provider") or declared["provider"]).lower().replace("-", "_")
    backend = setting("MN_VLM_BACKEND", "MN_LLM_BACKEND", default=declared.get("backend", "auto")
        if model == declared["model"] and provider == declared["provider"] else "auto")
    nim = backend.lower() == "nim" and provider != "ollama"
    dmr = not nim and provider in {"docker_model_runner", "dmr"}
    if dmr and not prompt.lstrip().startswith("/no_think"):
        prompt = "/no_think\n" + prompt
    options = {"provider": provider, "backend": backend,
        "api_base": setting("MN_VLM_API_BASE", "MN_LLM_API_BASE", "VL_MODEL_BASE_URL", "OLLAMA_BASE_URL",
            default=configured.get("api_base") or "auto"),
        "timeout_seconds": float(setting("MN_VLM_TIMEOUT_SECONDS", "MN_LLM_TIMEOUT_SECONDS", "OLLAMA_TIMEOUT_SECONDS", default=configured.get("timeout_seconds") or 90)),
        "api_key_env": "MN_VLM_API_KEY" if env.get("MN_VLM_API_KEY") else "MN_LLM_API_KEY"}
    temperature = float(setting("MN_VLM_TEMPERATURE", "OLLAMA_TEMPERATURE", default="0.0"))
    if provider == "ollama":
        refs = [block.store.commit_bytes(f"{block.root}/vision-inputs/{index}", frame, kind="model_media").to_dict()
            for index, frame in enumerate(frames)]
        payload = {"model": model.removeprefix("ollama/"), "prompt": prompt, "stream": False, "format": "json",
            "think": setting("OLLAMA_THINK", default="false").lower() in {"1", "true", "yes", "on"},
            "images": [{"$artifact": ref, "encoding": "base64"} for ref in refs],
            "options": {"temperature": temperature, "num_predict": int(setting("OLLAMA_NUM_PREDICT", default="300"))}}
        path = "/api/generate"
    else:
        content = model_user_content(prompt, frames, media_format="video_url" if nim else "image_url")
        # Freeze binary media separately so the effect intent stays small and
        # portable; model API data URIs are assembled by the SDK at dispatch.
        for index, item in enumerate(content):
            kind = item.get("type")
            if kind in {"image_url", "video_url"}:
                url = item[kind]["url"]
                header, encoded = url.split(";base64,", 1)
                ref = block.store.commit_bytes(f"{block.root}/vision-inputs/{index}",
                    base64.b64decode(encoded, validate=True), kind="model_media")
                item[kind]["url"] = {"$artifact": ref.to_dict(), "encoding": "data_uri", "mime_type": header.removeprefix("data:")}
        payload = {"model": model, "messages": [{"role": "user", "content": content}],
            "max_tokens": int(setting("MN_VLM_MAX_TOKENS", "MN_LLM_MAX_TOKENS", "OLLAMA_NUM_PREDICT", default="4096" if nim else "900")),
            "temperature": temperature}
        if nim:
            # Cosmos3 uses prompt-driven reasoning, not the Qwen template
            # switch. Routine monitoring requests the documented direct answer
            # mode to reserve its bounded output for the structured result.
            payload["messages"].insert(0, {"role": "system", "content":
                "Inspect the selected CCTV frames. Return only the requested compact JSON object. "
                "Describe visible people's actions and changes across the selected frames in detail. "
                "Do not output reasoning, Markdown or XML tags. Keep the summary and evidence concise, with explicit uncertainty."})
            payload.update(media_io_kwargs={"video": {"fps": 4.0}})
            options.update(model_spec=declared["model_spec"], required_capabilities=["image_input"])
        else:
            payload["response_format"] = {"type": "json_object"}
            options.update(structured_output=True, required_capabilities=["image_input", "structured_output"])
        if dmr:
            payload.update(chat_template_kwargs={"enable_thinking": False}, thinking_budget_tokens=0)
        path = "/chat/completions"
    return {"request": {"purpose": "vlm", "model": model, "path": path, "payload": payload, "options": options},
        "nim": nim, "ollama": provider == "ollama"}


def interpret(raw, prepared):
    if prepared["ollama"]:
        text = raw.get("response") or (raw.get("message") or {}).get("content") or ""
    else:
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") if isinstance(choice, dict) else {}
        text = str((message or {}).get("content") or "")
        if prepared["nim"]:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
            finish = choice.get("finish_reason")
            if finish == "length":
                raise ValueError("Cosmos returned incomplete video understanding: output limit reached")
            if re.search(r"<think>", text, re.IGNORECASE) or finish not in {None, "stop"}:
                raise ValueError("Cosmos returned incomplete video understanding")
            text = text.strip()
            opening = re.match(r"<answer>\s*", text, re.IGNORECASE)
            if opening:
                text = text[opening.end():]
                closing = re.search(r"\s*</answer>\s*$", text, re.IGNORECASE)
                if closing:
                    text = text[:closing.start()]
                elif finish != "stop":
                    raise ValueError("Cosmos returned incomplete video understanding")
            if re.search(r"</?answer>", text, re.IGNORECASE):
                raise ValueError("Cosmos returned incomplete video understanding")
            # Cosmos may stop after its final fenced JSON without emitting the
            # answer closing tag. JSON completeness, not that presentation tag,
            # establishes the boundary; never salvage a partial object.
            fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text.strip(), re.IGNORECASE)
            if fence:
                text = fence[1]
    if prepared["nim"]:
        try:
            result = json.loads(text)
        except (ValueError, TypeError) as error:
            raise ValueError("Model returned no valid structured detection") from error
        if not isinstance(result, dict):
            raise ValueError("Model returned no valid structured detection")
    else:
        result, error = parse_model_json(text)
        if result is None:
            raise ValueError("Model returned no valid structured detection: " + error)
    if prepared["nim"] and (not isinstance(result.get("scene_understanding"), str) or not result["scene_understanding"].strip()
        or not isinstance(result.get("risk_predictions"), list) or not isinstance(result.get("uncertainties"), list)):
        raise ValueError("Cosmos final answer is missing scene understanding, risk predictions or uncertainties")
    return normalize_detection(result)
