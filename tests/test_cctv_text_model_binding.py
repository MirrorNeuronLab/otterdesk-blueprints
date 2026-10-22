"""History questions retain the runtime's prepared text-model binding."""

import importlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


@pytest.mark.parametrize("summarize", [False, True])
@pytest.mark.parametrize("timeout,tokens,expected_timeout,expected_tokens", [
    (120, 1800, 60, 1024),
    (12, 256, 12, 256),
])
@pytest.mark.parametrize("provider,model", [
    ("litellm", "__mn_owner__/selected-owner/prepared-route"),
    ("openai", "registered/history-model"),
])
def test_history_dispatch_preserves_prepared_model_binding(
    monkeypatch, tmp_path, summarize, provider, model,
    timeout, tokens, expected_timeout, expected_tokens
):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    history = importlib.import_module("domain.video_questions")
    for name, value in {
        "MN_LLM_MODEL": model,
        "MN_LLM_PROVIDER": provider,
        "MN_LLM_BACKEND": "provider",
        "MN_LLM_API_BASE": "http://prepared-gateway.test/v1",
        "MN_LLM_API_KEY": "fixture-only-key",
        "MN_LLM_CONTEXT_SIZE": "16384",
        "MN_LLM_TIMEOUT_SECONDS": str(timeout),
        "MN_LLM_MAX_TOKENS": str(tokens),
        "MN_LLM_REQUIRED_CAPABILITIES_JSON": '["structured_output"]',
        "MN_LLM_STRUCTURED_OUTPUT_OPTIONS_JSON": json.dumps({
            "temperature": .2,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "history_answer", "schema": {"type": "object"},
            }},
            "chat_template_kwargs": {"enable_thinking": True, "custom_control": "keep"},
        }),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(history, "read_video_history", lambda *args, **kwargs: {
        "history": {"status": "ready", "evidence": [{"text": "A cart was parked."}]},
        "qualification": "Sampled history only.",
        "citations": {"m1": [{"source_id": "saved-observation"}]},
    })
    calls = []

    def dispatch(purpose, selected_model, path, payload, **options):
        calls.append((purpose, selected_model, path, payload, options))
        return {"choices": [{"message": {"content": json.dumps({
            "summary": "A cart was parked.", "citations": ["m1"],
        })}}]}

    monkeypatch.setattr("mn_sdk.llm.runtime_model_json_request", dispatch)
    # Catalog defaults are deliberately different from the already prepared
    # runtime binding, as with registered providers and selected-owner routes.
    config = json.loads((ROOT / "config/default.json").read_text())
    result = history.answer_video(config, tmp_path, "test-run", "What happened?", summarize=summarize)

    assert len(calls) == 1
    purpose, selected_model, path, payload, options = calls[0]
    assert purpose == "llm" and path == "/chat/completions"
    assert selected_model == model
    assert options["provider"] == provider
    assert options["backend"] == "provider"
    assert options["api_base"] == "http://prepared-gateway.test/v1"
    assert options["api_key"] == "fixture-only-key"
    assert options["context_size"] == 16384
    assert options["num_retries"] == 0 and options["timeout_seconds"] == expected_timeout
    assert options["required_capabilities"] == ("structured_output",)
    assert payload["max_tokens"] == expected_tokens
    assert payload["temperature"] == .2
    assert payload["response_format"]["json_schema"]["name"] == "history_answer"
    assert payload["chat_template_kwargs"] == {"enable_thinking": False, "custom_control": "keep"}
    assert result["summary"] == "A cart was parked.\n\nSampled history only."
    assert result["citations"][0]["citation"] == "m1"
    assert "fixture-only-key" not in json.dumps(result)
