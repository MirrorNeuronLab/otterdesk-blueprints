from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


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


def _run_detector(module, monkeypatch, tmp_path, capsys, *, payload, detection, state=None, message=None):
    run_dir = tmp_path / "run"
    batch_dir = run_dir / "frame_batches" / "batch-test"
    batch_dir.mkdir(parents=True)
    frame_path = batch_dir / "frame-01.jpg"
    frame_path.write_bytes(b"jpeg-frame")
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
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({"video_source": {"mode": "stream", "uri": "rtsp://camera.example/unit-test"}}),
    )
    monkeypatch.delenv("VIDEO_SOURCE_URI", raising=False)
    monkeypatch.setenv("SLACK_ALERT_ENABLED", "false")
    monkeypatch.delenv("MOCK_VLM_DETECTION", raising=False)
    monkeypatch.delenv("VISUAL_DETECTION_PROMPT", raising=False)
    def fake_call_ollama(_frame, prompt):
        prompts.append(prompt)
        return module.normalize_detection(detection)

    monkeypatch.setattr(module, "call_ollama", fake_call_ollama)

    module.main()
    output = json.loads(capsys.readouterr().out)
    return output, prompts


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


def test_cctv_operator_big_change_emits_chat_human_notice(monkeypatch, tmp_path, capsys):
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
        payload={"tick_seq": 5, "camera_id": "front-door"},
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
    assert notice["payload"]["kind"] == "video_big_change"
    assert notice["payload"]["chat_delivery"] == "otterdesk_worker_chat"
    assert notice["payload"]["title"] == "Big change in video"
    assert "2 people" in notice["payload"]["message"].lower()
    assert "front door" in notice["payload"]["message"].lower()


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
