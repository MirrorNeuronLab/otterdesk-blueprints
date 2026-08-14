from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
from mn_sdk import apply_manifest_config_bindings, expand_manifest_source

from workspace_paths import companion_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
SKILLS = WORKSPACE / "mn-skills"
for source in (
    SKILLS / "live_video_analysis_skill" / "src",
    SKILLS / "web_ui_skill" / "src",
    WORKSPACE / "mn-python-sdk",
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
    instruction_field = service.application.spec["elements"]["update-watch"][
        "props"
    ]["fields"][0]
    assert instruction_field["type"] == "textarea"
    assert instruction_field["max_length"] == 500


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
                "type": "cctv_operator_attention_updated",
                "payload": {
                    "instruction": "Watch the loading dock",
                    "instruction_revision": 3,
                },
            }
        )
        + "\n"
        + json.dumps(
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
    assert state["metrics"]["watch target"] == "Watch the loading dock"
    assert state["metrics"]["instruction revision"] == 3


def test_cctv_ui_state_prefers_durable_monitoring_state(tmp_path: Path):
    (tmp_path / "monitoring_state.json").write_text(
        json.dumps(
            {
                "schema": "otterdesk.cctv_operator.monitoring_state.v1",
                "instruction": "Monitor the left doorway.",
                "instruction_revision": 4,
                "last_command_id": "command-four",
                "updated_at": 42.0,
            }
        )
    )
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={},
        send_run_input=lambda *_args: {},
    )

    state = service.ui_state()

    assert state["metrics"]["watch target"] == "Monitor the left doorway."
    assert state["metrics"]["instruction revision"] == 4


def test_cctv_ui_projects_operator_status_from_durable_report(
    tmp_path: Path,
):
    observed_at = time.time()
    (tmp_path / "cctv_report.json").write_text(
        json.dumps(
            {
                "frames_analyzed": 7,
                "detection_count": 2,
                "observations": [
                    {
                        "frame_seq": 7,
                        "observed_at": observed_at,
                        "summary": "One person is visible.",
                        "confidence": 0.91,
                        "risk_level": "medium",
                    }
                ],
                "detections": [
                    {
                        "frame_seq": 7,
                        "observed_at": observed_at,
                        "summary": "One person entered the lobby.",
                        "confidence": 0.91,
                        "risk_level": "medium",
                    }
                ],
                "alerts": [
                    {
                        "frame_seq": 7,
                        "observed_at": observed_at,
                        "message": "Review the person entering the lobby.",
                        "matched_targets": ["person"],
                    }
                ],
                "errors": [],
                "sampling_metrics": {
                    "latest_model_latency_ms": 834,
                    "samples_skipped": 3,
                },
                "latest_batch": {
                    "sampling_trigger": "scene_event",
                    "selected_count": 4,
                },
            }
        )
    )
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-report",
        run_dir=tmp_path,
        config={
            "inputs": {"payload": {"visual_targets": ["person"]}},
            "sampling": {"baseline_interval_seconds": 20},
        },
        send_run_input=lambda *_args: {},
    )

    state = service.ui_state()

    assert state["metrics"]["status"] == "Review needed"
    assert state["metrics"]["frames analyzed"] == 7
    assert state["metrics"]["target detections"] == 2
    assert state["metrics"]["alerts to review"] == 1
    assert state["metrics"]["confidence"] == "91%"
    assert state["metrics"]["latest trigger"] == "scene_event"
    assert state["metrics"]["selected frames"] == 4
    assert state["metrics"]["model latency"] == "834 ms"
    assert any(
        event["type"] == "Operator notice"
        for event in state["events"]
    )


def test_cctv_ui_uses_external_browser_preview_without_local_relay(
    tmp_path: Path,
):
    preview_url = "http://camera-gateway:8888/cctv/index.m3u8"
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={
            "web_ui": {
                "preview": {
                    "enabled": True,
                    "url": preview_url,
                }
            }
        },
        send_run_input=lambda *_args: {},
    )

    preview = service.application.spec["elements"]["preview-video"]
    assert preview["type"] == "Video"
    assert preview["props"]["source"] == preview_url
    assert service.ui_state()["metrics"]["preview"] == "external"
    assert all(
        mount.url_prefix != "/preview"
        for mount in service.application.static_mounts
    )
    assert not (tmp_path / "preview_relay").exists()


def test_cctv_ui_without_preview_url_keeps_analysis_available(tmp_path: Path):
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={},
        send_run_input=lambda *_args: {},
    )

    preview = service.application.spec["elements"]["preview-video"]
    state = service.ui_state()
    assert preview["type"] == "Video"
    assert preview["props"]["source"] == ""
    assert preview["props"]["emptyLabel"] == "Live preview is blank"
    assert state["metrics"]["preview"] == "unavailable"
    assert "not configured" not in state["warning"]


def test_cctv_ui_uses_compact_operator_layout_and_keeps_evidence():
    spec = cctv_web_ui.build_ui_spec("https://camera.example/live.m3u8")
    elements = spec["elements"]

    assert elements["app"]["props"]["density"] == "compact"
    assert elements["layout"]["children"] == [
        "operations",
        "preview",
        "latest",
        "events",
        "controls",
        "boundary",
    ]
    assert elements["latest"]["props"]["span"] == 5
    assert elements["latest-image"]["type"] == "ArtifactImage"
    assert elements["events"]["props"]["span"] == 8
    assert elements["controls"]["props"]["span"] == 4
    assert elements["event-feed"]["props"]["limit"] == 16
    assert elements["status"]["props"]["keys"][0:3] == [
        "status",
        "watch target",
        "latest finding",
    ]


@pytest.mark.parametrize(
    "preview_url",
    [
        "rtsp://camera/live",
        "http://user:secret@camera/live/index.m3u8",
        "/preview/stream.m3u8",
    ],
)
def test_cctv_ui_rejects_non_browser_safe_preview_urls(
    tmp_path: Path,
    preview_url: str,
):
    with pytest.raises(ValueError, match="web_ui.preview.url"):
        cctv_web_ui.CCTVWebUIService(
            run_id="run-1",
            run_dir=tmp_path,
            config={"web_ui": {"preview": {"url": preview_url}}},
            send_run_input=lambda *_args: {},
        )


def test_cctv_ui_host_and_port_config_update_runtime_service_contract():
    blueprint = ROOT / "cctv_operator"
    source = json.loads((blueprint / "manifest.json").read_text())
    manifest = expand_manifest_source(source, root_dir=blueprint)
    config = json.loads((blueprint / "config" / "default.json").read_text())
    assert config["web_ui"]["service"]["host"] == "0.0.0.0"
    config["web_ui"]["service"]["port"] = 61017

    apply_manifest_config_bindings(manifest, config)

    node = next(
        item
        for item in manifest["agents"]["nodes"]
        if item["node_id"] == "cctv_web_ui"
    )
    assert node["services"][0]["address"] == "0.0.0.0"
    assert node["resources"]["ports"][0]["port"] == 61017
    assert node["services"][0]["port"] == 61017


def test_cctv_ui_uses_loopback_public_url_for_wildcard_listener():
    assert (
        cctv_web_ui.public_service_url("0.0.0.0", 61017)
        == "http://127.0.0.1:61017"
    )
    assert (
        cctv_web_ui.public_service_url(
            "0.0.0.0", 61017, "https://camera-ui.example/"
        )
        == "https://camera-ui.example"
    )
