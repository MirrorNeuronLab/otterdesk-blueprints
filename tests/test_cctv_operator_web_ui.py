from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT.parent / "mn-skills"
for source in (
    SKILLS / "live_video_analysis_skill" / "src",
    SKILLS / "web_ui_skill" / "src",
    ROOT.parent / "mn-python-sdk",
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

MODULE_PATH = (
    ROOT
    / "cctv_operator"
    / "payloads"
    / "services"
    / "cctv_web_ui.py"
)
SPEC = importlib.util.spec_from_file_location("cctv_web_ui", MODULE_PATH)
assert SPEC and SPEC.loader
cctv_web_ui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cctv_web_ui)


def test_cctv_ui_owns_steering_route_and_payload_validation(tmp_path: Path):
    calls = []

    def send(run_id, input_id, payload, idempotency_key):
        calls.append((run_id, input_id, payload, idempotency_key))
        return {"status": "accepted", "command_id": idempotency_key}

    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={"video_source": {"uri": "rtsp://user:secret@camera/live"}},
        send_run_input=send,
    )
    response = service.steer_monitoring(
        {"instruction": "Watch the left door", "analyze_now": True},
        "command-1",
    )
    assert response.status_code == 202
    assert calls == [
        (
            "run-1",
            "steer_monitoring",
            {
                "instruction": "Watch the left door",
                "analyze_now": True,
                "clear": False,
            },
            "command-1",
        )
    ]
    assert "steer-monitoring" in service.application.actions
    assert "/api/v1/runs" not in json.dumps(service.application.spec)


def test_cctv_ui_rejects_unknown_and_invalid_steering_fields():
    with pytest.raises(ValueError, match="unknown"):
        cctv_web_ui.validate_steering_payload({"agent_id": "detector"})
    with pytest.raises(ValueError, match="500"):
        cctv_web_ui.validate_steering_payload(
            {"instruction": "x" * 501}
        )
    with pytest.raises(ValueError, match="boolean"):
        cctv_web_ui.validate_steering_payload(
            {"instruction": "door", "analyze_now": "yes"}
        )


def test_cctv_ui_state_redacts_stream_credentials(tmp_path: Path):
    (tmp_path / "events.jsonl").write_text(
        json.dumps(
            {
                "type": "cctv_operator_frame_batch_ready",
                "payload": {
                    "summary": (
                        "Captured rtsp://user:secret@camera/live?token=hidden"
                    ),
                    "trigger": "scene_event",
                    "selected_count": 4,
                },
            }
        )
        + "\n"
    )
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={"video_source": {"uri": "rtsp://user:secret@camera/live"}},
        send_run_input=lambda *_args: {},
    )
    state = service.ui_state()
    encoded = json.dumps(state)
    assert "secret" not in encoded
    assert "token=" not in encoded
    assert state["metrics"]["latest trigger"] == "scene_event"
