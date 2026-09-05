from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from mn_sdk.blueprints import read_blueprint, resolve_config
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
for source in (
    WORKSPACE / "mn-skills" / "live_video_analysis_skill" / "src",
    WORKSPACE / "mn-skills" / "web_ui_skill" / "src",
    WORKSPACE / "mn-python-sdk",
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

MODULE_PATH = ROOT / "cctv_operator" / "payloads" / "services" / "cctv_web_ui.py"
SPEC = importlib.util.spec_from_file_location("cctv_web_ui", MODULE_PATH)
assert SPEC and SPEC.loader
cctv_web_ui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cctv_web_ui)


class StubPreview:
    enabled = True

    def __init__(self):
        self.stopped = False

    def frames(self):
        yield b"\xff\xd8preview-frame\xff\xd9"

    def snapshot(self):
        return {"status": "live", "warning": ""}

    def stop(self):
        self.stopped = True


def test_cctv_ui_state_redacts_stream_credentials_and_uses_durable_monitoring_state(
    tmp_path: Path,
):
    (tmp_path / "events.jsonl").write_text(
        json.dumps(
            {
                "type": "cctv_operator_frame_batch_ready",
                "payload": {"summary": "rtsp://user:secret@camera/live?token=hidden"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "monitoring_state.json").write_text(
        json.dumps(
            {
                "instruction": "Monitor the left doorway.",
                "instruction_revision": 4,
            }
        ),
        encoding="utf-8",
    )
    service = cctv_web_ui.CCTVWebUIService(run_id="run-1", run_dir=tmp_path, config={})

    state = service.ui_state()

    assert "secret" not in json.dumps(state)
    assert "token=" not in json.dumps(state)
    assert state["metrics"]["watch target"] == "Monitor the left doorway."


def test_cctv_ui_server_serves_mjpeg_sse_and_no_browser_action(tmp_path: Path):
    preview = StubPreview()
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={},
        preview_stream=preview,
    )
    server = cctv_web_ui.CCTVWebUIServer(service, host="127.0.0.1", port=0)
    host, port = server.address
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = urllib.request.urlopen(f"http://{host}:{port}/").read().decode()
        assert "CCTV Operator" in page
        assert "streams/live.mjpg" in page
        assert "streams/operator-events" in page
        assert "Operator event stream" in page
        assert "Change the watch" not in page
        assert "setInterval" not in page
        assert json.loads(
            urllib.request.urlopen(f"http://{host}:{port}/ui/state").read()
        )["metrics"]
        with urllib.request.urlopen(
            f"http://{host}:{port}/streams/live.mjpg"
        ) as response:
            assert response.headers.get_content_type() == "multipart/x-mixed-replace"
            assert response.headers.get_param("boundary") == cctv_web_ui.MJPEG_BOUNDARY
            assert b"preview-frame" in response.read()
        with urllib.request.urlopen(
            f"http://{host}:{port}/streams/operator-events"
        ) as response:
            lines = [response.readline().decode() for _ in range(4)]
            assert response.headers.get_content_type() == "text/event-stream"
            assert lines[0].startswith("id: ")
            assert lines[1] == "event: operator-state\n"
            assert lines[2].startswith("data: {")
        request = urllib.request.Request(
            f"http://{host}:{port}/actions/steer-monitoring",
            data=b"{}",
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        assert exc.value.code == 404
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://{host}:{port}/artifacts/not-allowed.jpg")
        assert exc.value.code == 404
    finally:
        server.stop()
        thread.join(timeout=2)
    assert preview.stopped is True


def test_cctv_ui_mjpeg_relay_uses_cuda_decode_and_scale_without_cpu_fallback():
    settings = cctv_web_ui.mjpeg_preview_settings(
        {
            "video_source": {"uri": "rtsp://camera.example/live"},
            "web_ui": {
                "preview": {
                    "fps": 9,
                    "width": 960,
                    "jpeg_quality": 4,
                }
            },
        }
    )
    command = cctv_web_ui.ffmpeg_mjpeg_command(settings)

    assert settings.enabled is True
    assert command[command.index("-hwaccel") + 1] == "cuda"
    assert command[command.index("-hwaccel_output_format") + 1] == "cuda"
    assert "scale_cuda=w=960:h=-2:format=nv12,hwdownload,format=nv12,fps=9" in command
    assert command[command.index("-c:v") + 1] == "mjpeg"
    assert "libx264" not in command
    assert "h264" not in command


def test_cctv_ui_mjpeg_relay_extracts_complete_jpegs_from_chunked_output():
    settings = cctv_web_ui.mjpeg_preview_settings({})
    preview = cctv_web_ui.CUDAMJPEGPreview(settings)

    preview._read_frames(
        io.BytesIO(b"noise\xff\xd8first\xff\xd9between\xff\xd8second\xff\xd9")
    )

    assert preview._latest_frame == b"\xff\xd8second\xff\xd9"
    assert preview.snapshot() == {"status": "live", "warning": ""}


def test_cctv_ui_operator_events_are_newest_first(tmp_path: Path):
    (tmp_path / "events.jsonl").write_text(
        "\n".join(
            json.dumps(event)
            for event in (
                {
                    "type": "video_monitor_start",
                    "timestamp": "2026-09-02T12:00:00Z",
                    "payload": {},
                },
                {
                    "type": "cctv_operator_report_ready",
                    "timestamp": "2026-09-02T12:00:05Z",
                    "payload": {},
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={},
        preview_stream=StubPreview(),
    )

    assert [event["type"] for event in service.ui_state()["events"]] == [
        "Report updated",
        "Monitor online",
    ]


def test_cctv_ui_uses_the_shared_dynamic_port_and_external_handle_contract():
    blueprint = ROOT / "cctv_operator"
    source = (blueprint / "payloads" / "services" / "cctv_web_ui.py").read_text(
        encoding="utf-8"
    )
    config = resolve_config(read_blueprint(blueprint)).data

    assert "resolve_web_ui_binding" in source
    assert "claim_web_ui" in source
    assert "json-render" not in source
    assert config["web_ui"]["service"]["port"] == 0


def test_cctv_ui_advertises_the_owner_node_for_host_network_workers(monkeypatch):
    monkeypatch.setenv("MN_EXECUTION_NODE", "mirror_neuron@10.0.4.26")
    monkeypatch.setenv("MN_DOCKER_WORKER_CONTAINER_NAME", "mn-dw-job-example-shared")

    assert cctv_web_ui.public_service_url("0.0.0.0", 45767) == "http://10.0.4.26:45767"
