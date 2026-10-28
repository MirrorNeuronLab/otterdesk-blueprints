"""Real CCTV request/interpretation policy with a synthetic model transport."""

import base64
import importlib
import json
from pathlib import Path

import pytest
from mn_blueprint_blocks.testing import BlockHarness
from mn_sdk.blueprints import blueprint_definition, read_blueprint
from mn_sdk.integrations import block_model_request

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"
ACCOUNT = {"detected_target": False, "confidence": .9, "summary": "A cart is parked.",
    "scene_understanding": "A cart is parked beside the aisle.", "risk_predictions": [], "uncertainties": []}


@pytest.fixture
def vision(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    module = importlib.import_module("domain.vision_model")
    descriptor = tmp_path / "runtime.json"
    descriptor.write_text(json.dumps(blueprint_definition(read_blueprint(ROOT))))
    harness = BlockHarness(tmp_path / "run")
    block = harness.context(environment={"MN_BLUEPRINT_MANIFEST_PATH": str(descriptor)})
    encoded = []
    def temporal(prompt, frames, *, media_format):
        encoded.append((prompt, frames, media_format))
        return [{"type": "text", "text": prompt},
            {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(b"temporal fixture").decode()}}]
    return harness, block, module, encoded, temporal


def test_nim_request_preserves_temporal_media_and_runtime_owned_route(vision, monkeypatch):
    harness, block, module, encoded, temporal = vision
    monkeypatch.setattr(module, "model_user_content", temporal)
    prepared = module.prepare(block, [b"earlier", b"later"], "Describe this window")
    request = prepared["request"]
    assert prepared["nim"] is True and prepared["ollama"] is False
    assert encoded == [("Describe this window", [b"earlier", b"later"], "video_url")]
    assert request["model"] == "cosmos3-nano-reasoner:1.7" and request["path"] == "/chat/completions"
    assert request["options"]["backend"] == "nim" and request["options"]["api_base"] == "auto"
    assert request["options"]["model_spec"]["docker"]["image"] == "nvcr.io/nim/nvidia/cosmos3-reasoner:1.7"
    payload = request["payload"]
    assert "response_format" not in payload
    assert payload["max_tokens"] == 4096
    assert "chat_template_kwargs" not in payload
    assert payload["messages"][0]["role"] == "system"
    assert "compact JSON" in payload["messages"][0]["content"]
    assert payload["media_io_kwargs"] == {"video": {"fps": 4.0}}
    media = payload["messages"][1]["content"][1]["video_url"]["url"]
    assert media["encoding"] == "data_uri" and media["mime_type"] == "video/mp4"
    assert harness.store.read_bytes(media["$artifact"]) == b"temporal fixture"
    calls = []
    def client(*args, **options):
        calls.append((args, options))
        return {"choices": [{"message": {"content": json.dumps(ACCOUNT)}}]}
    monkeypatch.setattr(block_model_request, "runtime_model_json_request", client)
    raw = block_model_request.model_request(block, request, key="scene")
    assert block_model_request.model_request(harness.context(environment=block.environment), request, key="scene") == raw
    assert len(calls) == 1 and calls[0][1]["num_retries"] == 0
    assert calls[0][0][3]["messages"][1]["content"][1]["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert module.interpret(raw, prepared)["scene_understanding"] == ACCOUNT["scene_understanding"]


def test_dmr_request_disables_thinking_and_keeps_image_capability(vision):
    harness, block, module, _encoded, _temporal = vision
    block.environment.update(MN_VLM_MODEL="alternative-vision", MN_VLM_PROVIDER="docker_model_runner",
        MN_VLM_BACKEND="docker", MN_VLM_MAX_TOKENS="900")
    prepared = module.prepare(block, [b"frame"], "Describe the evidence")
    payload = prepared["request"]["payload"]
    assert payload["messages"][0]["content"][0]["text"].startswith("/no_think\n")
    assert payload["thinking_budget_tokens"] == 0
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["response_format"] == {"type": "json_object"}
    assert prepared["request"]["options"]["required_capabilities"] == ["image_input", "structured_output"]
    assert prepared["request"]["options"]["structured_output"] is True
    image = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert harness.store.read_bytes(image["$artifact"]) == b"frame"


def test_explicit_ollama_uses_sdk_transport_and_never_uses_private_thinking(vision):
    harness, block, module, _encoded, _temporal = vision
    block.environment.update(MN_VLM_MODEL="ollama/alternative-vision", MN_VLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://approved-camera-model:11434", OLLAMA_NUM_PREDICT="321")
    prepared = module.prepare(block, [b"earlier", b"later"], "Review this window")
    request = prepared["request"]
    assert request["path"] == "/api/generate" and request["options"]["backend"] == "auto"
    assert request["payload"]["model"] == "alternative-vision"
    assert request["payload"]["think"] is False and request["payload"]["options"]["num_predict"] == 321
    assert [harness.store.read_bytes(value["$artifact"]) for value in request["payload"]["images"]] == [b"earlier", b"later"]
    assert module.interpret({"response": json.dumps(ACCOUNT)}, prepared)["summary"] == ACCOUNT["summary"]
    with pytest.raises(ValueError, match="no valid structured detection"):
        module.interpret({"thinking": json.dumps(ACCOUNT)}, prepared)


def test_nim_reasoning_is_excluded_from_public_interpretation(vision):
    _harness, _block, module, _encoded, _temporal = vision
    raw = {"choices": [{"finish_reason": "stop", "message": {"content":
        '<think>Private internal reasoning</think><answer>' + json.dumps(ACCOUNT) + '</answer>'}}]}
    result = module.interpret(raw, {"nim": True, "ollama": False})
    assert result["scene_understanding"] == ACCOUNT["scene_understanding"]
    assert "Private internal reasoning" not in json.dumps(result)


def test_nim_reasoning_tags_are_case_insensitive(vision):
    _harness, _block, module, _encoded, _temporal = vision
    account = json.dumps(ACCOUNT)
    raw = {"choices": [{"finish_reason": "stop", "message": {"content":
        '<THINK>Private internal reasoning</THINK><ANSWER>' + account + '</ANSWER>'}}]}
    result = module.interpret(raw, {"nim": True, "ollama": False})
    assert result["scene_understanding"] == ACCOUNT["scene_understanding"]


@pytest.mark.parametrize("wrapper", ["{account}", "```json\n{account}\n```"])
def test_nim_normal_stop_accepts_a_complete_answer_without_its_presentation_closing_tag(vision, wrapper):
    _harness, _block, module, _encoded, _temporal = vision
    content = "<think>Private internal reasoning</think><answer>" + wrapper.format(account=json.dumps(ACCOUNT))
    raw = {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
    result = module.interpret(raw, {"nim": True, "ollama": False})
    assert result["scene_understanding"] == ACCOUNT["scene_understanding"]
    assert "Private internal reasoning" not in json.dumps(result)


@pytest.mark.parametrize("content,finish,reason", [
    ("<think>unfinished", "stop", "incomplete"),
    (json.dumps(ACCOUNT), "length", "incomplete"),
    ("<answer>" + json.dumps(ACCOUNT), None, "incomplete"),
    ("<answer>" + json.dumps(ACCOUNT)[:-1], "stop", "no valid"),
    ("<answer>```json\n" + json.dumps(ACCOUNT), "stop", "no valid"),
    ("<answer>" + json.dumps(ACCOUNT) + " trailing prose", "stop", "no valid"),
    ("<answer><answer>" + json.dumps(ACCOUNT), "stop", "incomplete"),
    (json.dumps(ACCOUNT), "content_filter", "incomplete"),
    ("not JSON", "stop", "no valid"),
    ('{"summary":"No complete account"}', "stop", "missing scene"),
])
def test_known_invalid_model_response_is_not_a_clear_scene(vision, content, finish, reason):
    _harness, _block, module, _encoded, _temporal = vision
    raw = {"choices": [{"finish_reason": finish, "message": {"content": content}}]}
    with pytest.raises(ValueError, match=reason):
        module.interpret(raw, {"nim": True, "ollama": False})
