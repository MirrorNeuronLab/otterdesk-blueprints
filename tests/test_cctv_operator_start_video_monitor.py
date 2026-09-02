from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "cctv_operator"
    / "payloads"
    / "agents"
    / "validation"
    / "start_video_monitor.py"
)
SPEC = importlib.util.spec_from_file_location("start_video_monitor", MODULE_PATH)
assert SPEC and SPEC.loader
start_video_monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(start_video_monitor)


def test_start_message_validates_completes_step_and_routes(monkeypatch, capsys):
    monkeypatch.setattr(
        start_video_monitor,
        "load_json_env",
        lambda name: (
            {
                "type": "cctv_operator_start",
                "payload": {"stream_id": "demo"},
            }
            if name == "MN_INPUT_FILE"
            else {"envelope": {"type": "init"}}
        ),
    )
    monkeypatch.setattr(
        start_video_monitor,
        "validate_start",
        lambda: (True, "Bundled CCTV demo source accepted."),
    )

    assert start_video_monitor.main() == 0

    result = json.loads(capsys.readouterr().out)
    assert result["complete_step"]["stream_session"] == {
        "status": "ready",
        "stream_id": "demo",
    }
    assert result["emit_messages"] == [
        {"body": {"stream_id": "demo"}, "type": "cctv_operator_start"}
    ]


def test_steering_message_is_preserved_without_revalidation(monkeypatch, capsys):
    monkeypatch.setattr(
        start_video_monitor,
        "load_json_env",
        lambda name: (
            {"instruction": "Watch the left door", "analyze_now": True}
            if name == "MN_INPUT_FILE"
            else {"envelope": {"type": "cctv_operator_steer"}}
        ),
    )
    monkeypatch.setattr(
        start_video_monitor,
        "validate_start",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected validation")),
    )

    assert start_video_monitor.main() == 0

    result = json.loads(capsys.readouterr().out)
    assert result["emit_messages"] == [
        {
            "body": {
                "instruction": "Watch the left door",
                "analyze_now": True,
            },
            "type": "cctv_operator_steer",
        }
    ]
