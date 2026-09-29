"""Strict model access; no invented successful work on model failure."""
import json
from pathlib import Path
from mn_sdk.llm import LLMClient
from mn_sdk.blueprint_support.runtime import configured_llm_environment_scope


def generate(context, prompt_name, data):
    prompt = (Path(__file__).resolve().parents[1] / "prompts" / (prompt_name + ".md")).read_text()
    data = {**data, "common_goal": context["payload"].get("common_goal", "Market Bibblio through relevant, human-approved email outreach.")}
    with configured_llm_environment_scope(context["config"]):
        client = LLMClient.from_env(strict=True)
        client.timeout_seconds = 45
        client.num_retries = 0
        client.max_tokens = 2400
        result = client.completion_json(prompt, json.dumps(data, ensure_ascii=False))
    if not isinstance(result, dict):
        raise ValueError("The model did not return a usable marketing draft")
    return result
