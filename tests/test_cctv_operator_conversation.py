from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
DETECTOR_PATH = (
    ROOT
    / "cctv_operator"
    / "payloads"
    / "agents"
    / "visual_detector"
    / "scripts"
    / "analyze_video_frame.py"
)


def _load_detector():
    original_path = list(sys.path)
    original_domain_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == "domain" or key.startswith("domain.")
    }
    for key in original_domain_modules:
        sys.modules.pop(key, None)
    spec = importlib.util.spec_from_file_location("cctv_operator_analyze_video_frame", DETECTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
        for key in list(sys.modules):
            if key == "domain" or key.startswith("domain."):
                sys.modules.pop(key, None)
        sys.modules.update(original_domain_modules)
    return module


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _run_detector(
    module,
    monkeypatch,
    tmp_path,
    capsys,
    *,
    payload,
    detection,
    state=None,
    message=None,
    config=None,
    gate=None,
    review_approved=None,
):
    run_dir = tmp_path / "run"
    batch_dir = run_dir / "frame_batches" / "batch-test"
    batch_dir.mkdir(parents=True)
    frame_path = batch_dir / "frame-01.jpg"
    frame_path.write_bytes(b"\xff\xd8jpeg-frame\xff\xd9")
    batch_ref = "frame_batches/batch-test/batch.json"
    instruction = str(payload.get("instruction") or "")
    revision = int(payload.get("instruction_revision") or 0)
    _write_json(
        batch_dir / "batch.json",
        {
            "schema": "otterdesk.cctv_operator.frame_batch.v2",
            "batch_id": "batch-test",
            "trigger": "on_demand" if instruction else "baseline",
            "source": {
                "mode": "stream",
                "uri": "rtsp://camera.example/unit-test",
                "name": "rtsp://camera.example/unit-test",
                "position_seconds": 0,
            },
            "instruction": instruction,
            "instruction_revision": revision,
            "candidate_count": 1,
            "selected_count": 1,
            "selected_frames": [
                {
                    "path": "frame_batches/batch-test/frame-01.jpg",
                    "timestamp": 1.0,
                    "score": 0.5,
                    "sha256": "test",
                }
            ],
            "metrics": {},
        },
    )
    payload = {
        **payload,
        "batch_id": "batch-test",
        "frame_batch_ref": batch_ref,
        "trigger": "on_demand" if instruction else "baseline",
        "candidate_count": 1,
        "selected_count": 1,
    }
    input_file = _write_json(tmp_path / "input.json", payload)
    message_file = _write_json(tmp_path / "message.json", message or {"stream": {"stream_id": "unit-stream"}})
    context_file = _write_json(tmp_path / "context.json", {"agent_state": state or module.initial_state()})
    prompts: list[str] = []

    monkeypatch.setenv("MN_INPUT_FILE", str(input_file))
    monkeypatch.setenv("MN_MESSAGE_FILE", str(message_file))
    monkeypatch.setenv("MN_CONTEXT_FILE", str(context_file))
    monkeypatch.setenv("MN_RUN_DIR", str(run_dir))
    monkeypatch.setenv("MN_RUN_ID", "test-run")
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps(
            config
            or {
                "video_source": {
                    "mode": "stream",
                    "uri": "rtsp://camera.example/unit-test",
                }
            }
        ),
    )
    monkeypatch.delenv("VIDEO_SOURCE_URI", raising=False)
    monkeypatch.setenv("SLACK_ALERT_ENABLED", "false")
    monkeypatch.delenv("MOCK_VLM_DETECTION", raising=False)
    monkeypatch.delenv("VISUAL_DETECTION_PROMPT", raising=False)
    def fake_call_ollama(_frame, prompt, *, response_schema=None):
        if response_schema:
            return gate or {"condition_met": True, "confidence": 0.95}
        prompts.append(prompt)
        matched = detection.get("detected_target", detection.get("detected")) is True
        return module.normalize_detection({"goal_event": {"start_frame": 1, "end_frame": 1, "evidence_frame": 1} if matched else None, **detection})

    monkeypatch.setattr(module, "call_ollama", fake_call_ollama)
    if review_approved is not None:
        monkeypatch.setattr(module, "await_operator_review", lambda **_kwargs: review_approved)

    module.main()
    output = json.loads(capsys.readouterr().out)
    return output, prompts


def test_quiet_scene_is_analyzed_without_target_screening(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "camera_id": "entrance"},
        detection={"detected": False, "confidence": .9, "summary": "The aisle remains clear.",
                   "scene_understanding": "A parked cart remains beside the aisle."},
        gate={"condition_met": False, "confidence": .94})
    assert len(prompts) == 1
    observed = output["next_state"]["last_observation"]
    assert observed["scene_understanding"] == "A parked cart remains beside the aisle."
    assert observed["condition_screening"]["mode"] == "independent_captioning"
    assert not any(event["type"] == "human_input_requested" for event in output["events"])


def test_uncertain_scene_does_not_block_observation_for_approval(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 2, "camera_id": "entrance"},
        detection={"detected": False, "confidence": .3, "summary": "The aisle is obscured.",
                   "uncertainties": ["Occlusion prevents assessing clearance."]},
        review_approved=False)
    assert len(prompts) == 1
    assert output["next_state"]["last_observation"]["uncertainties"] == ["Occlusion prevents assessing clearance."]
    assert not any(event["type"] == "human_input_requested" for event in output["events"])


def test_cctv_operator_chat_context_answers_what_happened(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, _prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={"tick_seq": 9, "camera_id": "loading-dock"},
        detection={
            "detected": True,
            "detected_target": True,
            "detection_count": 2,
            "detections": [
                {
                    "label": "person",
                    "category": "person",
                    "color": "blue jacket",
                    "position": "left side of the loading dock",
                    "activity": "walking into view",
                    "confidence": 0.91,
                },
                {
                    "label": "person",
                    "category": "person",
                    "color": "dark hoodie",
                    "position": "center of the loading dock",
                    "activity": "following behind",
                    "confidence": 0.89,
                },
            ],
            "confidence": 0.92,
            "summary": "Two people appeared in the loading dock view.",
            "detection_report": "Two people appeared near the loading dock entrance.",
            "activity_description": "Both people are walking into the monitored area.",
            "risk_level": "medium",
            "visible_subjects": ["person", "person"],
        },
    )

    context = output["next_state"]["conversation_context"]
    assert "frame 9" in context["what_happened"].lower()
    assert "two people appeared near the loading dock entrance" in context["what_happened"].lower()
    assert any(event["type"] == "cctv_operator_frame_observed" for event in output["events"])
    assert output["events"][-1]["type"] == "cctv_operator_detection"
    observed = next(
        event["payload"]
        for event in output["events"]
        if event["type"] == "cctv_operator_frame_observed"
    )
    assert observed["frame_batch_ref"] == (
        "frame_batches/batch-test/batch.json"
    )
    assert observed["batch_id"] == "batch-test"
    assert observed["selected_count"] == 1
    assert observed["model_latency_ms"] >= 0
    assert observed["observed_at"].endswith("Z")


def test_monitoring_goal_match_emits_timed_chat_notice_with_frame(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    previous_state = detector.initial_state()
    previous_state["last_observation"] = {
        "frame_seq": 4,
        "camera_id": "front-door",
        "detected_target": False,
        "detection_count": 0,
        "person_like_count": 0,
        "risk_level": "low",
    }

    output, _prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={"tick_seq": 5, "camera_id": "front-door", "instruction": "People entering the front door.", "instruction_revision": 1},
        state=previous_state,
        detection={
            "detected": True,
            "detected_target": True,
            "detection_count": 2,
            "detections": [
                {
                    "label": "person",
                    "category": "person",
                    "color": "white shirt",
                    "position": "near the front door",
                    "activity": "standing at the entrance",
                    "confidence": 0.94,
                },
                {
                    "label": "person",
                    "category": "person",
                    "color": "black jacket",
                    "position": "behind the first person",
                    "activity": "entering the frame",
                    "confidence": 0.9,
                },
            ],
            "confidence": 0.94,
            "summary": "Two people appeared at the entrance.",
            "detection_report": "Two people are visible near the front door.",
            "activity_description": "One person is standing while another enters the frame.",
            "risk_level": "medium",
            "visible_subjects": ["person", "person"],
        },
    )

    notice = next(event for event in output["events"] if event["type"] == "human_notice")
    assert notice["channel"] == "human"
    assert notice["payload"]["kind"] == "configured_target_detection"
    assert notice["payload"]["chat_delivery"] == "otterdesk_worker_chat"
    assert notice["payload"]["title"] == "Monitoring goal detected"
    assert "two people" in notice["payload"]["message"].lower()
    assert "front door" in notice["payload"]["message"].lower()
    assert notice["payload"]["observed_at"] == "1970-01-01T00:00:01Z"
    assert "1970-01-01T00:00:01Z" in notice["payload"]["message"]
    assert notice["payload"]["image"]["mime_type"] == "image/jpeg"
    assert notice["payload"]["image"]["run_id"] == "test-run"
    assert notice["payload"]["monitoring_goal"] == "People entering the front door."
    assert not (tmp_path / "run/web/conversation_media.json").exists()


def test_continuing_goal_match_is_not_repeated_after_cooldown(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = {**detector.initial_state(), "notified_goal": "A person is visible in the video."}
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 3}, state=state,
        detection={"detected_target": True, "confidence": .95, "summary": "The group is still standing together."})
    assert not any(event["type"] == "human_notice" for event in output["events"])
    assert output["next_state"]["notified_goal"] == state["notified_goal"]


def test_confirmed_goal_absence_rearms_notifications(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = {**detector.initial_state(), "notified_goal": "A person is visible in the video."}
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 3}, state=state,
        detection={"detected_target": False, "confidence": .95, "summary": "The group dispersed."})
    assert output["next_state"]["notified_goal"] is None


@pytest.mark.parametrize("matched,confidence,cooldown", [(False, .95, 0), (True, .3, 0), (True, .95, 120)])
def test_unrelated_low_confidence_and_repeated_activity_stay_quiet(monkeypatch, tmp_path, capsys, matched, confidence, cooldown):
    detector = _load_detector()
    state = detector.initial_state()
    state["last_alert_wall_ts"] = __import__("time").time() if cooldown else 0
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 2}, state=state,
        detection={"detected_target": matched, "confidence": confidence,
                   "detections": [{"label": "person", "category": "person"}],
                   "summary": "People are visible.", "scene_understanding": "People are visible."})
    assert "A person is visible in the video." in prompts[0]
    assert not any(event["type"] == "human_notice" for event in output["events"])
    assert not (tmp_path / "run/web/conversation_media.json").exists()


def test_cctv_operator_user_attention_request_changes_prompt_and_state(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={
            "tick_seq": 3,
            "camera_id": "warehouse-aisle",
            "instruction": "Pay attention to the red backpack near the left doorway.",
            "instruction_revision": 1,
        },
        detection={
            "detected": False,
            "detected_target": False,
            "detection_count": 0,
            "detections": [],
            "confidence": 0.2,
            "summary": "No configured targets are visible yet.",
            "risk_level": "low",
            "visible_subjects": [],
        },
    )

    assert prompts and "red backpack near the left doorway" in prompts[0]
    assert output["next_state"]["attention_instruction"] == "Pay attention to the red backpack near the left doorway."
    assert output["next_state"]["conversation_context"]["attention_instruction"] == (
        "Pay attention to the red backpack near the left doorway."
    )
    attention_event = next(event for event in output["events"] if event["type"] == "cctv_operator_attention_updated")
    assert "red backpack" in attention_event["payload"]["summary"]
    assert output["events"][-1]["type"] == "cctv_operator_frame_observed"


def test_new_person_goal_not_blocked_by_previous_alert_cooldown(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = detector.initial_state()
    state["last_alert_wall_ts"] = __import__("time").time()
    output, _ = _run_detector(
        detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 3, "camera_id": "entrance", "instruction": "Find a person", "instruction_revision": 1},
        state=state,
        detection={
            "detected": True, "detected_target": True, "detection_count": 1,
            "detections": [{"label": "person", "category": "person", "confidence": 0.93}],
            "confidence": 0.93, "summary": "A person is visible.",
            "detection_report": "A person is visible at the entrance.",
            "visible_subjects": ["person"], "risk_level": "low",
        },
    )
    notices = [event for event in output["events"] if event["type"] == "human_notice"]
    assert len(notices) == 1
    assert "person" in notices[0]["payload"]["message"].lower()


def test_cctv_operator_uses_configured_targets_and_notice_policy(
    monkeypatch, tmp_path, capsys
):
    detector = _load_detector()
    output, prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={"tick_seq": 2, "camera_id": "lobby"},
        config={
            "video_source": {
                "mode": "stream",
                "uri": "rtsp://camera.example/unit-test",
            },
            "inputs": {
                "payload": {
                    "monitoring_goal": "red backpack",
                    "visual_targets": ["red backpack"],
                    "alert_policy": {
                        "mode": "human_notice_only",
                        "min_confidence": 0.8,
                        "cooldown_seconds": 120,
                        "notify_on": ["red backpack"],
                    },
                }
            },
        },
        detection={
            "detected": True,
            "detected_target": True,
            "detection_count": 1,
            "detections": [
                {
                    "label": "red backpack",
                    "category": "unattended package",
                    "color": "red",
                    "position": "left side",
                    "activity": "stationary",
                    "confidence": 0.93,
                }
            ],
            "confidence": 0.93,
            "summary": "A red backpack is visible in the lobby.",
            "detection_report": "A red backpack is stationary on the left.",
            "risk_level": "medium",
            "visible_subjects": ["red backpack"],
        },
    )

    assert "red backpack" in prompts[0].lower()
    detection_event = next(
        event
        for event in output["events"]
        if event["type"] == "cctv_operator_detection"
    )
    assert detection_event["payload"]["configured_targets"] == [
        "red backpack"
    ]
    assert detection_event["payload"]["alert_decision"]["notify"] is True
    notice = next(
        event for event in output["events"] if event["type"] == "human_notice"
    )
    assert notice["payload"]["kind"] == "configured_target_detection"
    assert notice["payload"]["matched_targets"] == ["red backpack"]
    assert not any(
        str(event["type"]).startswith("cctv_operator_slack_alert_")
        for event in output["events"]
    )


def test_cctv_operator_batch_revision_can_clear_attention_state():
    detector = _load_detector()
    state = {
        **detector.initial_state(),
        "attention_instruction": "Watch the red backpack.",
        "attention_targets": ["Watch the red backpack."],
        "instruction_revision": 1,
    }

    event = detector.apply_attention_request(
        state,
        {"instruction": "", "instruction_revision": 2},
        {},
        "camera-1",
    )

    assert state["attention_instruction"] == ""
    assert state["attention_targets"] == []
    assert state["instruction_revision"] == 2
    assert event["payload"]["cleared"] is True


def test_cctv_setup_offers_sample_and_secure_external_source():
    ui = json.loads((ROOT / "cctv_operator/extensions/ui.json").read_text())
    guide = ui["setup_guide"]
    assert guide["sample"]["available"] is True
    assert guide["sample"]["values"]["video_source.profile"] == "bundled_demo"
    assert guide["real"]["values"]["video_source.profile"] == "external"
    fields = {field["path"]: field for field in guide["fields"]}
    stream = fields["video_source.uri"]
    assert stream["secret"] is True
    assert stream["required"] is True
    assert stream["active_when_any"] == [{"key": "video_source.profile", "equals": "external"}]
    assert set(stream["protocols"]) == {"rtsp:", "rtsps:", "rtmp:", "rtmps:"}
    assert all(not field["required"] for key, field in fields.items()
               if key not in {"video_source.profile", "video_source.uri", "video_source.demo_file", "inputs.payload.monitoring_goal"})


def test_floor_focus_replaces_default_targets_in_model_request(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    instruction = "can you focus on find foreign object on the floor?"
    monkeypatch.setenv("VISUAL_DETECTION_TARGETS", "person, vehicle")
    output, prompts = _run_detector(
        detector, monkeypatch, tmp_path, capsys,
        payload={"instruction": instruction, "instruction_revision": 2,
                 "command_id": "floor-focus"},
        detection={"detected": False, "detected_target": False,
                   "detections": [], "detection_count": 0, "confidence": 0.8,
                   "summary": "No foreign object is visible on the floor.",
                   "risk_level": "low"},
    )
    targets = prompts[0].split("## Targets\n", 1)[1].split("## Current analysis goal", 1)[0]
    assert targets.strip() == instruction
    assert "person, vehicle" not in prompts[0]
    assert output["next_state"]["attention_instruction"] == instruction
    assert output["next_state"]["instruction_revision"] == 2
    restored = detector.detection_prompt("camera", "", ["person"])
    assert "person, vehicle" in restored
    assert instruction not in restored


def test_chat_planner_receives_steering_semantics_from_normalized_contract(tmp_path):
    from mn_sdk_common.response_service import normalize_response_service
    from mn_sdk_job_response.agent_planner import AgentPlanner
    from mn_sdk_job_response.agent_memory import AgentMemory
    from mn_sdk_job_response.agent_store import AgentStore

    source = json.loads((ROOT / "cctv_operator/extensions/response.json").read_text())
    source.pop("$schema")
    declaration = normalize_response_service({"response_service": source})["agent"]
    store = AgentStore(tmp_path / "conversation.sqlite3", "cctv-test")
    memory = AgentMemory(declaration=declaration, store=store,
                         job_data_dir=tmp_path, rag_refresh=lambda: None)
    planner = AgentPlanner(declaration=declaration, store=store, memory=memory)
    question = "can you focus on find foreign object on the floor?"
    prompt = json.loads(planner.user_prompt(question, {}, [], ""))
    tools = prompt["allowed_user_tools"]
    assert question in tools["set_monitoring_instruction"]["description"]
    assert "change the goal to watch the corridor" in tools["set_monitoring_instruction"]["description"]
    assert "Quiet and unrelated activity produce no chat messages" in tools["watch_operator_activity"]["description"]
    assert 'Never use "latest"' in tools["get_operator_activity"]["description"]
    assert "command_id" not in tools["set_monitoring_instruction"]["arguments"]
    assert "action" in prompt["turn_contract"]["allowed_intents"]
    plan = planner.validate_plan({
        "intent": "action", "tool": "set_monitoring_instruction",
        "arguments": {"instruction": question, "clear": "false", "analyze_now": "true"},
    }, question)
    assert plan["arguments"]["instruction"] == question
    assert plan["arguments"]["command_id"]
