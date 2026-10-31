"""Real CCTV request/interpretation policy with a synthetic model transport."""

import base64
import importlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
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


def test_edge_requests_bind_one_real_frame_and_reserve_policy_budget(vision, monkeypatch):
    harness, block, module, encoded, _temporal = vision
    prepared = module.prepare(block, [b"earlier", b"later"], "AUTHORITATIVE TIMES AND HISTORY", goal="A person without a helmet")
    requests = prepared["perception_requests"]
    assert len(requests) == 2 and not encoded
    assert sum(r["payload"]["max_tokens"] for r in requests) + prepared["policy_request"]["payload"]["max_tokens"] <= 4096
    for request, frame in zip(requests, [b"earlier", b"later"]):
        assert request["model"] == "cosmos3-edge:bf16" and request["path"] == "/chat/completions"
        assert request["options"]["backend"] == "vllm" and request["options"]["api_base"] == "auto"
        assert request["options"]["model_spec"]["docker"]["image"].startswith("vllm/vllm-openai@sha256:")
        assert request["options"]["required_capabilities"] == ["image_input"]
        payload = request["payload"]
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert "response_format" not in payload
        content = payload["messages"][0]["content"]
        assert len(content) == 2 and "A person without a helmet" in content[1]["text"]
        assert "AUTHORITATIVE TIMES AND HISTORY" not in content[1]["text"]
        assert harness.store.read_bytes(content[0]["image_url"]["url"]["$artifact"]) == frame
    policy = prepared["policy_request"]
    assert policy["purpose"] == "llm" and policy["model"] != requests[0]["model"]
    assert policy["payload"]["messages"][1]["content"] == "AUTHORITATIVE TIMES AND HISTORY"
    assert policy["payload"]["response_format"]["json_schema"]["strict"] is True


def test_frame_and_policy_effects_replay_without_more_inference(vision, monkeypatch):
    harness, block, module, _encoded, _temporal = vision
    scene = importlib.import_module("domain.scene_analysis")
    prepared = module.prepare(block, [b"earlier", b"later"], "Review current evidence")
    calls = []
    account = {**ACCOUNT, "detections": [], "goal_event": None, "helmet_observations": [], "site_findings": []}
    def client(*args, **options):
        calls.append((args, options))
        content = "A cart is parked by the aisle." if args[0] == "vlm" else json.dumps(account)
        return {"choices": [{"finish_reason": "stop", "message": {"content": content, "reasoning": "PRIVATE"}}]}
    monkeypatch.setattr(block_model_request, "runtime_model_json_request", client)
    from domain.benchmarks import Benchmarks
    metrics = Benchmarks(harness.store.run_dir, {})
    raw, metadata, error = scene.analyze(block, prepared, metrics, frames=2, revision=1)
    replay = scene.analyze(harness.context(environment=block.environment), prepared, metrics, frames=2, revision=1)
    assert replay == (raw, metadata, error) and error is None
    assert len(calls) == 3 and all(options["num_retries"] == 0 for _, options in calls)
    evidence = json.loads(calls[-1][0][3]["messages"][-1]["content"])["current_selected_frame_evidence"]
    assert [item["frame"] for item in evidence] == [1, 2]
    assert "PRIVATE" not in json.dumps(evidence)
    assert module.interpret(raw, prepared)["scene_understanding"] == ACCOUNT["scene_understanding"]
    assert metadata["duration_seconds"] == metadata["perception_seconds"] + metadata["decision_seconds"]


@pytest.mark.parametrize("finish,content", [("length", "A partial account"), ("stop", ""), ("stop", "<think>private</think>")])
def test_incomplete_frame_evidence_never_dispatches_a_policy_request(vision, monkeypatch, finish, content):
    harness, block, module, _encoded, _temporal = vision
    scene = importlib.import_module("domain.scene_analysis")
    prepared = module.prepare(block, [b"one", b"two"], "Review")
    calls = []
    def client(*args, **options):
        calls.append(args[0])
        return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}
    monkeypatch.setattr(block_model_request, "runtime_model_json_request", client)
    from domain.benchmarks import Benchmarks
    raw, metadata, error = scene.analyze(block, prepared, Benchmarks(harness.store.run_dir, {}), frames=2, revision=1)
    assert raw is None and error and calls == ["vlm"]
    assert metadata["decision_seconds"] == 0


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


@pytest.mark.parametrize("count", [1, 3, 5, 7, 8])
def test_frame_evidence_is_not_duplicated_or_renumbered_by_the_model(vision, count):
    harness, block, module, _encoded, _temporal = vision
    frames = [f"selected-{index}".encode() for index in range(count)]
    original = list(frames)
    prepared = module.prepare(block, frames, "Selected capture times are authoritative.")
    actual = [harness.store.read_bytes(request["payload"]["messages"][0]["content"][0]["image_url"]["url"]["$artifact"])
              for request in prepared["perception_requests"]]
    assert actual == original == frames
    evidence = importlib.import_module("domain.frame_perception")
    observations = [evidence.observation({"choices": [{"finish_reason": "stop", "message": {
        "content": "A person is standing; model caption says Frame 0."}}]}, i) for i in range(1, count + 1)]
    policy = evidence.decision_request(prepared, observations)
    assert [item["frame"] for item in json.loads(policy["payload"]["messages"][-1]["content"])["current_selected_frame_evidence"]] == list(range(1, count+1))
    with pytest.raises(ValueError, match="every selected frame"):
        evidence.decision_request(prepared, observations[:-1])
    assert sum(r["payload"]["max_tokens"] for r in prepared["perception_requests"]) + policy["payload"]["max_tokens"] <= 4096


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
    ('{"summary":"No complete account"}', "stop", "scene_understanding must be a nonempty string"),
])
def test_known_invalid_model_response_is_not_a_clear_scene(vision, content, finish, reason):
    _harness, _block, module, _encoded, _temporal = vision
    raw = {"choices": [{"finish_reason": finish, "message": {"content": content}}]}
    with pytest.raises(ValueError, match=reason):
        module.interpret(raw, {"nim": True, "ollama": False})


@pytest.mark.parametrize("field,value,reason", [
    ("scene_understanding", "", "scene_understanding must be a nonempty string"),
    ("scene_understanding", [], "scene_understanding must be a nonempty string"),
    ("risk_predictions", {}, "risk_predictions must be a list"),
    ("uncertainties", "The person's hands are occluded.", "uncertainties must be a list of strings"),
    ("uncertainties", [42], "uncertainties must be a list of strings"),
])
def test_nim_names_the_invalid_field_without_discarding_it_as_a_missing_scene(vision, field, value, reason):
    _harness, _block, module, _encoded, _temporal = vision
    raw = {"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps({**ACCOUNT, field: value})}}]}
    with pytest.raises(ValueError, match=reason):
        module.interpret(raw, {"nim": True, "ollama": False})


def test_nim_generation_contract_covers_the_live_type_errors_and_original_frame_scope(vision, monkeypatch):
    _harness, block, module, _encoded, temporal = vision
    monkeypatch.setattr(module, "model_user_content", temporal)
    block.config["site"] = {"profile": "factory", "rule_ids": ["group_presence"]}
    prepared = module.prepare(block, [b"one", b"two", b"three"], "Review the selected evidence")
    schema = prepared["schema"]
    Draft202012Validator.check_schema(schema)
    validate = Draft202012Validator(schema).validate
    prediction = {"risk": "Possible contact with the cart", "visible_evidence": "A person approaches a cart in frames 1 and 3.",
        "time_horizon": "If the movement continues", "confidence": .6, "severity": "low",
        "recommended_review": "Review the original footage.", "evidence_frames": [1, 3]}
    account = {**ACCOUNT, "detections": [], "goal_event": None, "helmet_observations": [],
        "site_findings": [], "risk_predictions": [prediction], "uncertainties": ["Hands are occluded."]}
    validate(account)
    assert module.interpret({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(account)}}]},
        prepared)["uncertainties"] == account["uncertainties"]
    for invalid in (
        {**account, "uncertainties": "Hands are occluded."},
        {**account, "detections": [{"label": "Person", "category": "person", "color": "white",
            "position": "Repeated scene account. " * 100, "activity": "Standing", "confidence": .9}]},
        {**account, "risk_predictions": [{**prediction, "severity": "Low"}]},
        {**account, "risk_predictions": [{**prediction, "evidence_frames": [4]}]},
        {**account, "site_findings": [{"rule_id": "blocked_route", "status": "observed", "confidence": .9,
            "visible_evidence": "A cart is visible.", "evidence_frames": [1]}]},
        {key: value for key, value in account.items() if key != "scene_understanding"},
    ):
        with pytest.raises(ValidationError):
            validate(invalid)
    # XGrammar cannot enforce uniqueItems; the existing evidence validator must
    # still reject duplicates after generation instead of inventing provenance.
    assert "uniqueItems" not in json.dumps(schema)
    def bounded_strings(value):
        if isinstance(value, dict):
            if value.get("type") == "string":
                assert 0 < value["maxLength"] <= 1800
            for child in value.values():
                bounded_strings(child)
        elif isinstance(value, list):
            for child in value:
                bounded_strings(child)
    bounded_strings(schema)
    duplicated = {**account, "risk_predictions": [{**prediction, "evidence_frames": [1, 1]}]}
    validate(duplicated)
    result = module.normalize_detection(duplicated)
    site = importlib.import_module("domain.site_monitoring")
    batch = {"selected_frames": [{"timestamp": 100 + i, "path": f"{i}.jpg"} for i in range(3)]}
    with pytest.raises(ValueError, match="valid selected evidence_frames"):
        site.enrich(result, batch, block.config, "", "")
    block.config["site"] = {"profile": "custom"}
    custom = module.prepare(block, [b"one", b"two"], "Review")
    assert custom["schema"]["properties"]["site_findings"]["maxItems"] == 0


@pytest.mark.parametrize("private_field", ["reasoning", "reasoning_content"])
def test_native_reasoning_field_never_enters_the_public_observation(vision, private_field):
    _harness, _block, module, _encoded, _temporal = vision
    raw = {"choices": [{"finish_reason": "stop", "message": {
        private_field: "PRIVATE MODEL REASONING",
        "content": json.dumps(ACCOUNT),
    }}]}
    result = module.interpret(raw, {"nim": True, "ollama": False})
    assert result["scene_understanding"] == ACCOUNT["scene_understanding"]
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("confidence", "PRIVATE BAD VALUE"), ("uncertainties", "PRIVATE BAD VALUE"),
    ("goal_event", {"start_frame": 0, "end_frame": 1, "evidence_frame": 1})])
def test_policy_schema_failure_is_explicit_and_never_contains_response_text(vision, field, value):
    _harness, block, module, _encoded, _temporal = vision
    prepared = module.prepare(block, [b"frame"], "Review")
    account = {**ACCOUNT, "detections": [], "goal_event": None, "helmet_observations": [], "site_findings": [], field: value}
    with pytest.raises(ValueError, match=field) as error:
        module.interpret({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(account)}}]}, prepared)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("raw", [None, {}, {"choices": "bad"}, {"choices": [None]}, {"choices": [{"message": "bad"}]}])
def test_malformed_received_frame_response_is_a_known_failure(vision, raw):
    evidence = importlib.import_module("domain.frame_perception")
    with pytest.raises(ValueError, match="complete frame evidence"):
        evidence.observation(raw, 1)
