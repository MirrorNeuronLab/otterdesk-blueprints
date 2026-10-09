"""Offline Cosmos video transport, qualified forecasts and durable chat history."""

import hashlib
import json

import pytest

from test_cctv_operator_conversation import _load_detector, _run_detector


PREDICTION = {"risk": "Possible cart-pedestrian collision", "severity": "high", "confidence": .72,
              "visible_evidence": "A moving cart and pedestrian approach the same aisle crossing.",
              "time_horizon": "If the sampled movement continues over the next few seconds",
              "recommended_review": "Review the crossing in the original video before intervening."}


def test_cosmos_preserves_temporal_frames_and_only_publishes_final_answer(monkeypatch):
    detector = _load_detector()
    captured = {}
    monkeypatch.setenv("MN_VLM_MODEL", "cosmos3-nano-reasoner:1.7")
    monkeypatch.setenv("MN_VLM_BACKEND", "nim")
    monkeypatch.setenv("MN_VLM_PROVIDER", "docker_model_runner")
    monkeypatch.setenv("MN_VLM_API_BASE", "auto")
    def request(purpose, model, path, payload, **options):
        captured.update(payload=payload, options=options, model=model, purpose=purpose)
        return {"choices": [{"finish_reason": "stop", "message": {"content":
            '<think>PRIVATE DRAFT {"summary":"wrong draft"}</think><answer>' +
            json.dumps({"summary": "A cart approaches the crossing.", "scene_understanding": "The pedestrian and cart approach each other.",
                        "risk_predictions": [PREDICTION], "uncertainties": ["Distance cannot be measured."]}) + '</answer>'}}]}
    monkeypatch.setattr(detector, "runtime_model_json_request", request)
    from types import SimpleNamespace
    def encode(command, **kwargs):
        assert kwargs["input"] == b"firstsecond"
        assert kwargs["timeout"] == 10
        return SimpleNamespace(returncode=0, stdout=b"temporal-mp4", stderr=b"")
    monkeypatch.setattr("mn_live_video_analysis_skill.video_content.shutil.which", lambda _: "ffmpeg")
    monkeypatch.setattr("mn_live_video_analysis_skill.video_content.subprocess.run", encode)
    result = detector.call_ollama([b"first", b"second"], "Inspect the chronological sequence.")
    media = captured["payload"]["messages"][0]["content"]
    assert media[1] == {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,dGVtcG9yYWwtbXA0"}}
    assert captured["payload"]["media_io_kwargs"] == {"video": {"fps": 4.0}}
    assert captured["options"]["backend"] == "nim"
    assert captured["options"]["required_capabilities"] == ("image_input",)
    assert captured["payload"]["max_tokens"] == 4096
    assert "response_format" not in captured["payload"]
    assert "thinking_budget_tokens" not in captured["payload"]
    assert captured["payload"]["chat_template_kwargs"]["enable_thinking"] is True
    assert "PRIVATE DRAFT" not in json.dumps(result) and result["summary"] != "wrong draft"
    assert result["risk_predictions"][0]["qualification"] == "prediction_not_observed_event"


@pytest.mark.parametrize("change", [{"confidence": float("nan")}, {"visible_evidence": ""}, {"time_horizon": ""}, {"severity": "certain"}])
def test_forecasts_require_visible_support_and_finite_confidence(change):
    detector = _load_detector()
    with pytest.raises(ValueError):
        detector.normalize_detection({"summary": "A cart is visible.", "risk_predictions": [{**PREDICTION, **change}]})


def test_forecast_is_saved_when_no_target_matches_and_recalled_across_runs(monkeypatch, tmp_path, capsys, text_memory_transport):
    detector = _load_detector()
    config = {"text_memory": {"enabled": True, "max_context_bytes": 49152},
              "video_source": {"profile": "bundled_demo"}}
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "camera_id": "warehouse"}, config=config,
        detection={"detected_target": False, "confidence": .8, "summary": "A cart approaches a crossing.",
                   "scene_understanding": "A cart and pedestrian approach the aisle crossing.", "risk_predictions": [PREDICTION]})
    observed = output["next_state"]["last_observation"]
    assert observed["detected_target"] is False
    assert observed["risk_predictions"][0]["risk"] == PREDICTION["risk"]
    assert observed["observed_at"] == observed["capture_ended_at"]
    assert "Chronological selected video frames" in prompts[0]
    journal = next((tmp_path / "run/context_sources/outputs").glob("*.md"))
    assert PREDICTION["risk"] in journal.read_text() and "not observed events" in journal.read_text()
    source = hashlib.sha256(b"rtsp://camera.example/unit-test").hexdigest()
    monkeypatch.setenv("MN_RUN_ID", "next-run")
    memory = detector.CameraMemory(config, tmp_path / "next", "warehouse", source)
    packet = memory.recall("history", limit=12)
    assert PREDICTION["risk"] in json.dumps(packet)
    assert "frame_batches/batch-test/batch.json" in json.dumps(packet)
    memory.close()


def test_markdown_replay_is_idempotent_and_time_bounds_are_typed(tmp_path, text_memory_transport):
    detector = _load_detector()
    memory = detector.CameraMemory({"text_memory": {"enabled": True, "max_context_bytes": 49152}}, tmp_path, "camera", "source")
    observation = {"frame_seq": 1, "batch_id": "one", "camera_id": "camera", "observed_at": "2026-10-06T10:00:00Z",
                   "scene_understanding": "The floor is clear.", "risk_predictions": [], "condition_screening": {"route": "deep_analysis"}}
    memory.remember(observation)
    journal = next((tmp_path / "context_sources/outputs").glob("*.md"))
    before = journal.read_bytes()
    memory.remember(observation)
    assert journal.read_bytes() == before
    original = memory.memory.client.retrieve
    seen = {}
    def retrieve(request):
        seen.update(request)
        # This test exercises the native typed plan; the fixture supports eq only.
        copied = json.loads(json.dumps(request))
        copied["stages"][0]["analytical"]["filters"] = [f for f in copied["stages"][0]["analytical"]["filters"] if f["op"] == "eq"]
        return original(copied)
    memory.memory.client.retrieve = retrieve
    memory.recall("chat", after="2026-10-06T05:00:00-04:00", before="2026-10-06T11:00:00Z", limit=12)
    filters = seen["stages"][0]["analytical"]["filters"]
    assert {"field": "timestamp", "op": "gte", "value": "2026-10-06T09:00:00Z"} in filters
    assert {"field": "timestamp", "op": "lte", "value": "2026-10-06T11:00:00Z"} in filters
    with pytest.raises(ValueError, match="timezone"):
        memory.recall("invalid", after="2026-10-06T09:00:00")
    memory.close()


def test_chat_tool_reads_saved_scene_and_forecast_across_runs(monkeypatch, tmp_path, capsys, text_memory_transport):
    from test_cctv_operator_web_ui import StubPreview, cctv_web_ui

    detector = _load_detector()
    config = {"text_memory": {"enabled": True, "max_context_bytes": 49152},
              "video_source": {"profile": "bundled_demo", "camera_id": "warehouse", "uri": "rtsp://camera.example/unit-test"}}
    _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "camera_id": "warehouse"}, config=config,
        detection={"summary": "A cart approaches the crossing.", "scene_understanding": "A pedestrian approaches the same crossing.",
                   "risk_predictions": [PREDICTION], "uncertainties": ["Speed cannot be measured."]})
    monkeypatch.setenv("MN_RUN_ID", "chat-run")
    service = cctv_web_ui.CCTVWebUIService(run_id="chat-run", run_dir=tmp_path / "chat", config=config, preview_stream=StubPreview())

    class Server:
        def __init__(self, *args, **kwargs):
            self.tools = {}
        def tool(self, name=None, **kwargs):
            def register(function):
                self.tools[name or function.__name__] = function
                return function
            return register
        def resource(self, *args, **kwargs):
            return lambda function: function

    server = cctv_web_ui.create_operator_mcp_server(service, job_id="test-memory-job", run_id="chat-run",
        run_dir=tmp_path / "chat", server_factory=Server)
    history = server.tools["get_video_history"]()
    assert history["history"]["status"] == "ready"
    assert "A pedestrian approaches the same crossing." in json.dumps(history)
    assert PREDICTION["risk"] in json.dumps(history)
    assert "frame_batches/batch-test/batch.json" in json.dumps(history)
    assert "not observed events" in history["qualification"]
    with pytest.raises(ValueError, match="timezone"):
        server.tools["get_video_history"](after="2026-10-06T09:00:00")
    with pytest.raises(ValueError, match="precede"):
        server.tools["get_video_history"](after="2026-10-07T09:00:00Z", before="2026-10-06T09:00:00Z")

    # The current-run question lane reuses context memory and the text model,
    # with no frame retrieval or second vision pass.
    history_reader = cctv_web_ui._load_domain_function("runtime_memory", "CameraMemory")
    memory = history_reader(config, tmp_path / "chat", "warehouse",
        hashlib.sha256(b"rtsp://camera.example/unit-test").hexdigest())
    memory.remember({"frame_seq": 2, "camera_id": "warehouse", "batch_id": "two",
        "observed_at": "2026-10-07T10:00:00Z", "summary": "One person crosses the aisle.",
        "condition_screening": {"route": "deep_analysis"}, "frame_batch_ref": "frame_batches/two/batch.json"})
    memory.close()
    answer = cctv_web_ui._load_domain_function("video_questions", "answer_video")
    calls = []
    def text(system, user, **kwargs):
        prompt = json.loads(user)
        calls.append(prompt)
        assert "One person crosses the aisle" in user
        assert PREDICTION["risk"] not in user  # earlier run remains history-only
        return kwargs["validator"]({"summary": "One person crossed at 10:00; unique people so far cannot be determined.", "citations": ["m1"]})
    monkeypatch.setitem(answer.__globals__, "completion_json", text)
    class InlineThread:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(answer.__globals__["threading"], "Thread", InlineThread)
    command = "11111111-1111-4111-8111-111111111111"
    assert server.tools["answer_video_question"](command, "How many people appeared so far?")["state"] == "accepted"
    result = server.tools["get_video_answer"](command)
    assert result["state"] == "completed" and "cannot be determined" in result["summary"]
    assert result["evidence"]["citations"][0]["sources"]
    summary_command = "22222222-2222-4222-8222-222222222222"
    assert server.tools["get_video_summary"](summary_command)["state"] == "accepted"
    assert server.tools["get_video_answer"](summary_command)["state"] == "completed"
    assert len(calls) == 2 and calls[1]["summarize"] is True


def test_markdown_rollover_keeps_writing_and_replay_does_not_duplicate(monkeypatch, tmp_path):
    from test_cctv_operator_web_ui import cctv_web_ui

    publish = cctv_web_ui._load_domain_function("runtime_memory", "publish_camera_markdown")
    monkeypatch.setitem(publish.__globals__, "CAMERA_MARKDOWN_MAX_BYTES", 400)
    observation = {"observed_at": "2026-10-06T10:00:00Z", "camera_node_id": "camera"}
    for seq in range(3):
        publish({}, tmp_path, {**observation, "observation_id": str(seq)}, "account " + str(seq) + " x" * 60)
    files = sorted((tmp_path / "context_sources/outputs").glob("*.md"))
    assert len(files) > 1
    before = {path.name: path.read_bytes() for path in files}
    publish({}, tmp_path, {**observation, "observation_id": "2"}, "account 2" + " x" * 60)
    assert {path.name: path.read_bytes() for path in files} == before
    assert all(len(body) <= 400 for body in before.values())
    assert sum(body.count(b"<!-- observation:") for body in before.values()) == 3
