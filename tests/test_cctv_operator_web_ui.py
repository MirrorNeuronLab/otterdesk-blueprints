from __future__ import annotations

import importlib
import asyncio
import base64
import io
import json
import sys
import threading
import time
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
    WORKSPACE / "mn-python-sdk" / "packages" / "mcp" / "src",
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

MODULE_PATH = ROOT / "cctv_operator" / "payloads" / "services" / "cctv_web_ui.py"
SERVICES_DIR = MODULE_PATH.parent
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))
cctv_web_ui = importlib.import_module("cctv_operator.payloads.services.cctv_web_ui")
cctv_operator_mcp = importlib.import_module("cctv_operator.payloads.services.cctv_operator_mcp")


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


def test_private_mcp_starts_on_loopback_with_authenticated_relay(monkeypatch, tmp_path):
    from types import SimpleNamespace
    proxy_module = cctv_operator_mcp

    bindings = []
    listener = SimpleNamespace(close=lambda: None)
    def open_listener(host):
        bindings.append(host)
        return listener, 45670

    def create_server(_service, **kwargs):
        # Exercise the real SDK bind restriction that rejected production startup.
        from mn_sdk_mcp import create_mrtr_mcp_server
        return create_mrtr_mcp_server("test", host=kwargs["host"], port=kwargs["port"])

    def create_proxy(endpoint, **kwargs):
        assert endpoint["url"] == "http://127.0.0.1:45670"
        assert kwargs["access_token"]
        return SimpleNamespace(server_address=("0.0.0.0", 45671), serve_forever=lambda: None)

    monkeypatch.setattr(cctv_web_ui, "_open_listener", open_listener)
    monkeypatch.setattr(cctv_web_ui, "create_operator_mcp_server", create_server)
    monkeypatch.setattr(proxy_module, "create_mcp_proxy", create_proxy)
    monkeypatch.setattr(cctv_web_ui.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: None))
    # The production service also owns its activity-publishing thread. Supply
    # that interface while this test isolates the real SDK bind restriction.
    service = SimpleNamespace(publish_activity_until_stopped=lambda: None)
    cctv_web_ui.start_operator_mcp_server(service, job_id="job-1", run_id="run-1", run_dir=tmp_path)
    assert bindings == ["127.0.0.1"]
    artifact = tmp_path / cctv_web_ui.CCTV_MCP_ENDPOINT_ARTIFACT
    endpoint = cctv_operator_mcp.read_endpoint(artifact)
    assert endpoint["url"] == "http://host.docker.internal:45671"
    assert endpoint["token"]
    assert artifact.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("upstream_token", ["", "private-upstream-secret"])
def test_mcp_relay_requires_token_and_forwards_to_loopback(monkeypatch, upstream_token):
    from types import SimpleNamespace

    requests = []
    class Connection:
        def __init__(self, host, port, **kwargs):
            assert (host, port) == ("127.0.0.1", 45670)
        def request(self, method, path, body=None, headers=None):
            requests.append(headers)
        def getresponse(self):
            return SimpleNamespace(status=200, read=lambda n: b'{}', getheaders=lambda: [("Content-Type", "application/json")])
        def close(self):
            pass

    monkeypatch.setattr(cctv_operator_mcp, "HTTPConnection", Connection)
    server = cctv_operator_mcp.create_mcp_proxy(
        {"url": "http://127.0.0.1:45670", "token": upstream_token}, host="127.0.0.1", port=0, access_token="test-secret"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            opener.open(url)
        assert error.value.code == 403
        assert not requests
        request = urllib.request.Request(url, data=b'{}', headers={"X-CCTV-MCP-Token": "test-secret"})
        with opener.open(request) as response:
            assert response.status == 200
        assert requests[0]["Host"] == "127.0.0.1:45670"
        assert requests[0].get("X-CCTV-MCP-Token", "") == upstream_token
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_monitoring_command_uses_authenticated_host_control_bridge(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MN_RUN_ID", "execution-1")
    monkeypatch.setenv("MN_WORKFLOW_RUN_ID", "physical-run-2")
    command_id = "11111111-1111-4111-8111-111111111111"
    command = {"command_id": command_id, "instruction": "Find road obstructions.",
               "clear": False, "analyze_now": True}
    calls = []
    server = cctv_operator_mcp.create_mcp_proxy(
        {"url": "http://127.0.0.1:45670", "token": "private-token", "run_id": "run-1"},
        host="127.0.0.1", port=0,
        run_input_sender=lambda run_id, payload: calls.append((run_id, payload)) or {"status": "accepted"},
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (tmp_path / cctv_operator_mcp.CCTV_MCP_ENDPOINT_ARTIFACT).write_text(json.dumps({
        "url": "http://host.docker.internal:45670", "token": "private-token",
    }), encoding="utf-8")
    (tmp_path / cctv_operator_mcp.CCTV_CONTROL_ARTIFACT).write_text(json.dumps({
        "url": f"http://127.0.0.1:{server.server_address[1]}/control/steer",
    }), encoding="utf-8")
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/control/steer",
                    data=json.dumps(command).encode(),
                )
            )
        assert error.value.code == 403
        assert cctv_operator_mcp.send_monitoring_input(tmp_path, command) == {"status": "accepted"}
        assert calls == [("execution-1", command)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_monitoring_command_rejects_non_loopback_control_endpoint(tmp_path: Path):
    (tmp_path / cctv_operator_mcp.CCTV_MCP_ENDPOINT_ARTIFACT).write_text(json.dumps({
        "url": "http://host.docker.internal:45670", "token": "private-token",
    }), encoding="utf-8")
    (tmp_path / cctv_operator_mcp.CCTV_CONTROL_ARTIFACT).write_text(json.dumps({
        "url": "http://host.docker.internal:45671/control/steer",
    }), encoding="utf-8")
    with pytest.raises(RuntimeError, match="sidecar is unavailable"):
        cctv_operator_mcp.send_monitoring_input(tmp_path, {})


def test_cctv_mcp_sidecar_accepts_only_private_endpoint_and_proxy_clients(
    tmp_path: Path,
):
    route = tmp_path / "route"
    route.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        "eth0 00000000 010011AC 0003 0 0 0 00000000 0 0 0\n",
        encoding="utf-8",
    )

    endpoint = tmp_path / cctv_operator_mcp.CCTV_MCP_ENDPOINT_ARTIFACT
    endpoint.write_text(
        json.dumps({"url": "http://host.docker.internal:45678"}),
        encoding="utf-8",
    )
    assert cctv_operator_mcp.read_endpoint(endpoint) == {
        "url": "http://host.docker.internal:45678",
        "port": 45678,
    }
    endpoint.write_text(json.dumps({"url": "https://example.com:45678"}), encoding="utf-8")
    assert cctv_operator_mcp.read_endpoint(endpoint) is None
    assert cctv_operator_mcp.allowed_proxy_clients(route) == frozenset(
        {"127.0.0.1", "::1", "172.17.0.1"}
    )


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
        assert "Latest analyzed snapshot" in page
        assert 'id="analysis-status" role="status"' in page
        assert 'id="pipeline-warning" role="alert" hidden' in page
        assert '<time id="analyzed-at" hidden>' in page
        assert 'id="scene-analysis" aria-labelledby="scene-heading" hidden' in page
        assert 'id="scene-understanding"' in page
        assert 'id="risk-predictions"' in page
        assert 'id="uncertainties"' in page
        assert 'id="person-status" role="status"' in page
        assert 'id="person-history" hidden' in page
        assert 'id="caption-status"' in page
        assert page.index('aria-label="Live video"') < page.index('aria-labelledby="status-heading"')
        assert page.index('id="analysis-status"') < page.index('<summary>Latest analyzed snapshot')
        assert '<details open' not in page
        assert "Operator event stream" not in page
        assert "Latest finding" not in page
        assert "Confidence" not in page
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


def test_live_ui_exposes_person_detection_before_any_scene_report(tmp_path):
    now = time.time()
    (tmp_path / "person_detector_state.json").write_text(json.dumps({
        "person_detector": "running", "captions": "running",
        "last_person_frame_at": now, "visible_people": 1}))
    (tmp_path / "caption_schedule.json").write_text(json.dumps({
        "inflight": {"claimed_at": now - 20}, "inflight_status": "processing"}))
    (tmp_path / "events.jsonl").write_text(json.dumps({
        "type": "cctv_operator_person_event", "payload": {
            "purpose": "person_gate_only", "person_event": {
                "kind": "person_presence_started", "confirmed_at": now - 1, "person_count": 1}}}) + "\n")
    service = cctv_web_ui.CCTVWebUIService(run_id="run-1", run_dir=tmp_path,
        config={}, preview_stream=StubPreview())
    state = service.ui_state()
    assert state["pipeline"]["person_events"]["summary"] == "1 person detected in the latest sampled frame."
    assert state["pipeline"]["person_events"]["last_presence"]["person_count"] == 1
    assert state["pipeline"]["captions"]["summary"].startswith("Scene analysis in progress")
    assert state["metrics"]["frames analyzed"] == 0
    assert state["metrics"]["alerts to review"] == 0


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
    assert "fps=9,scale_cuda=w=960:h=-2:format=nv12,hwdownload,format=nv12" in command
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


def test_hiding_browser_preview_does_not_disable_shared_camera_capture():
    settings = cctv_web_ui.mjpeg_preview_settings({
        "video_source": {"uri": "rtsp://camera.example/live"},
        "web_ui": {"preview": {"enabled": False}},
    })
    assert settings.enabled is True
    assert "rtsp://camera.example/live" in cctv_web_ui.ffmpeg_mjpeg_command(settings)


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


@pytest.mark.parametrize("observations", [[], [{"summary": "A person walks past, without a group standing together.", "observed_at": "2026-09-08T22:23:39Z"}]])
def test_quiet_and_unrelated_activity_never_publish_chat_updates(tmp_path, observations):
    (tmp_path / "cctv_report.json").write_text(json.dumps({"observations": observations, "alerts": []}))
    service = cctv_web_ui.CCTVWebUIService(run_id="run-1", run_dir=tmp_path, config={}, preview_stream=StubPreview())
    published = []
    class Store:
        def publish_result(self, *args, **kwargs):
            published.append(args)
    service.attach_activity_store(Store())
    for now in (0, 30, 60, 600, 3600):
        assert service.sync_mcp_activity(now=now) == []
    assert published == []


def test_cctv_operator_owns_an_sdk_mcp_activity_exchange(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MN_RUN_ID", "execution-1")
    (tmp_path / "cctv_report.json").write_text(
        json.dumps(
            {
                "detections": [
                    {
                        "detection_report": "A person is visible near the center of the frame.",
                        "observed_at": "2026-09-08T22:23:39Z",
                        "confidence": 0.92,
                        "risk_level": "low",
                    }
                ],
                "alerts": [{
                    "message": "A person is visible near the center of the frame.",
                    "observed_at": "2026-09-08T22:23:39Z",
                    "confidence": 0.92,
                    "risk_level": "low",
                }],
            }
        ),
        encoding="utf-8",
    )
    service = cctv_web_ui.CCTVWebUIService(
        run_id="run-1",
        run_dir=tmp_path,
        config={},
        preview_stream=StubPreview(),
    )
    class FakeRuntime:
        def send_run_input(self, run_id, input_id, payload, *, idempotency_key):
            assert (run_id, input_id) == ("execution-1", "steer_monitoring")
            assert payload == {
                "command_id": idempotency_key,
                "instruction": "Find foreign objects on the floor.",
                "clear": False,
                "analyze_now": True,
            }
            assert idempotency_key == "11111111-1111-4111-8111-111111111111"
            return {"status": "accepted"}

    server = cctv_web_ui.create_operator_mcp_server(
        service,
        job_id="job-1",
        run_id="run-1",
        run_dir=tmp_path,
        runtime_service=FakeRuntime(),
        server_factory=lambda *args, **kwargs: type(
            "FakeServer",
            (),
            {
                "tools": {},
                "resources": {},
                "tool": lambda self, name=None, **_kw: lambda fn: self.tools.setdefault(name or fn.__name__, getattr(fn, "__wrapped__", fn)) or fn,
                "resource": lambda self, uri, **_kw: lambda fn: self.resources.setdefault(uri, fn) or fn,
            },
        )(),
    )

    status = server.tools["get_operator_status"]()
    assert status["status"] == service.ui_state()["metrics"]["status"]
    assert status["finding"] == "A person is visible near the center of the frame."
    assert status["observed_at"] == "2026-09-08T22:23:39Z"
    assert status["ready"] is True
    assert status["details"] == [{"label": "Confidence", "value": "92%"}, {"label": "Risk", "value": "low"}]
    assert status["finding"] in status["summary"]
    assert status["observed_at"] in status["summary"]
    person_answer = server.tools["get_operator_status"]("Do you see any person?")
    assert person_answer["summary"] == status["summary"]
    (tmp_path / "person_detector_state.json").write_text(json.dumps({
        "person_detector": "running", "last_person_frame_at": time.time(), "visible_people": 0,
        "captions": "running"}))
    current_person_answer = server.tools["get_operator_status"]("Do you see any person?")
    assert status["finding"] in current_person_answer["summary"]
    assert "No person detected in the latest sampled frame" in current_person_answer["summary"]
    assert current_person_answer["pipeline"]["person_events"]["visible_people"] == 0

    activity = server.tools["get_operator_activity"](0)

    assert set(server.tools) == {
        "acknowledge_operator_notice",
        "get_operation_status",
        "get_operator_activity",
        "get_operator_status",
        "get_pipeline_benchmarks",
        "get_video_history",
        "get_video_summary",
        "answer_video_question",
        "get_operation_status",
        "set_monitoring_instruction",
        "watch_job_activity",
    }
    receipt = server.tools["set_monitoring_instruction"](
        "11111111-1111-4111-8111-111111111111",
        "Find foreign objects on the floor.",
        False,
        True,
    )
    assert receipt["state"] == "accepted"
    assert "queued" in receipt["summary"]
    pending_status = server.tools["get_operation_status"]("11111111-1111-4111-8111-111111111111")
    assert "not been confirmed as applied" in pending_status["summary"]
    assert receipt["command_id"] == "11111111-1111-4111-8111-111111111111"
    (tmp_path / "monitoring_state.json").write_text(
        json.dumps(
            {
                "instruction": "Find foreign objects on the floor.",
                "instruction_revision": 2,
                "last_command_id": "11111111-1111-4111-8111-111111111111",
            }
        ),
        encoding="utf-8",
    )
    command_status = server.tools["get_operation_status"](
        "11111111-1111-4111-8111-111111111111"
    )
    assert command_status["state"] == "completed"
    assert command_status["instruction_revision"] == 2
    assert command_status["analysis_ready"] is False
    assert "The monitoring goal is now: Find foreign objects on the floor." in command_status["summary"]
    assert "not available yet" in command_status["summary"]
    with (tmp_path / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "cctv_operator_detection", "payload": {
            "instruction_revision": 2, "summary": "A foreign object is visible on the floor."
        }}) + "\n")
    updated_status = server.tools["get_operation_status"](
        "11111111-1111-4111-8111-111111111111"
    )
    assert updated_status["analysis_ready"] is True
    assert updated_status["latest_finding"] == "A foreign object is visible on the floor."
    assert updated_status["latest_finding"] in updated_status["summary"]
    assert activity["updates"][-1]["payload"] == {
        "schema_version": "mn.mcp.job_activity.v1",
        "event_id": activity["updates"][-1]["record_id"],
        "title": "Operator notice",
        "message": "A person is visible near the center of the frame.",
        "occurred_at": "2026-09-08T22:23:39Z",
        "source": "cctv_operator",
        "requires_review": True,
        "details": [{"label": "Confidence", "value": "92%"}, {"label": "Risk", "value": "low"}],
    }


def test_cctv_ui_uses_the_shared_dynamic_port_and_external_handle_contract():
    blueprint = ROOT / "cctv_operator"
    source = (blueprint / "payloads" / "domain" / "live_service.py").read_text(
        encoding="utf-8"
    )
    config = resolve_config(read_blueprint(blueprint)).data

    assert "resolve_web_ui_binding" in source
    assert "claim_service_web_ui" in source
    assert "json-render" not in source
    assert config["web_ui"]["service"]["port"] == 0


def test_activity_watch_delivers_image_and_advances_beyond_200_events(tmp_path):
    class Server:
        def __init__(self, *args, **kwargs):
            self.tools = {}
        def tool(self, name=None, **kwargs):
            def register(fn):
                self.tools[name or fn.__name__] = getattr(fn, "__wrapped__", fn)
                return fn
            return register
        def resource(self, *args, **kwargs):
            return lambda fn: fn

    service = cctv_web_ui.CCTVWebUIService(run_id="run-1", run_dir=tmp_path, config={}, preview_stream=StubPreview())
    server = cctv_web_ui.create_operator_mcp_server(service, job_id="job-1", run_id="run-1", run_dir=tmp_path, server_factory=Server)
    store = service._activity_store
    image = {"run_id": "run-1", "mime_type": "image/jpeg", "title": "Frame 241", "alt": "Group standing together",
             "caption": "Observed at 2026-01-01T00:00:02Z", "data": base64.b64encode(b"\xff\xd8frame\xff\xd9").decode()}
    for index in range(241):
        event_id = f"event-{index}"
        store.publish_result(event_id, {"event_id": event_id, "message": "Group standing together.", "notice_id": f"notice-{index}",
                              "image": image, "requires_review": True}, stage="goal_event", idempotency_key=event_id, publication_state="final")
    watched = asyncio.run(server.tools["watch_job_activity"]("event-239", 0))
    request = next(iter(watched.input_requests.values()))
    event = json.loads(request.params.requested_schema["properties"]["mn_activity"]["default"])
    assert event["event_id"] == "event-240"
    assert event["image"] == image
    assert event["notice_id"] == "notice-240"
    idle = asyncio.run(server.tools["watch_job_activity"]("event-240", 0))
    assert idle["delivered"] is False
    assert idle["cursor"] == "event-240"
    newest = asyncio.run(server.tools["watch_job_activity"]("", 0))
    assert json.loads(newest.request_state)["activity"]["event_id"] == "event-240"
    history = server.tools["get_operator_activity"](0)
    assert len(history["updates"]) == 20
    assert all("image" not in update["payload"] for update in history["updates"])


def test_preview_readiness_requires_first_frame(monkeypatch):
    settings = cctv_web_ui.mjpeg_preview_settings({})
    preview = cctv_web_ui.CUDAMJPEGPreview(settings)
    monkeypatch.setattr(preview, "ensure_started", lambda: None)
    assert preview.wait_for_first_frame(timeout_seconds=0.01) is False
    preview._publish(b"\xff\xd8frame\xff\xd9")
    assert preview.wait_for_first_frame(timeout_seconds=0.01) is True


def test_cctv_ui_advertises_the_owner_node_for_host_network_workers(monkeypatch):
    monkeypatch.setenv("MN_EXECUTION_NODE", "mirror_neuron@10.0.4.26")
    monkeypatch.setenv("MN_DOCKER_WORKER_CONTAINER_NAME", "mn-dw-job-example-shared")

    assert cctv_web_ui.public_service_url("0.0.0.0", 45767) == "http://10.0.4.26:45767"


def test_observation_details_belong_to_each_event_not_the_latest_frame():
    from cctv_operator.payloads.domain.dashboard import operator_state
    state = operator_state(run_id="run-1", config={}, report={
        "detections": [
            {"summary": "Earlier observation", "confidence": 0.62, "risk_level": "low", "observed_at": 1},
            {"summary": "Later observation", "confidence": 0.94, "risk_level": "medium", "observed_at": 2},
        ]}, latest_frame={}, monitoring={}, supplemental_events=[], preview_status="live", preview_warning="")
    events = state["events"]
    assert events[0]["details"][0] == {"label": "Confidence", "value": "94%"}
    assert events[1]["details"][0] == {"label": "Confidence", "value": "62%"}


def test_confirmed_notice_keeps_the_detailed_activity_account_in_chat(tmp_path):
    from cctv_operator.payloads.domain.detection_policy import configured_target_notice
    from cctv_operator.payloads.domain.dashboard import operator_state

    account = " ".join([
        "In frame 1, the person in blue stands on the left, holding a box with both hands.",
        "In frames 2 and 3, they turn toward the open aisle and carry the box away from the shelf.",
        "The person in gray remains beside the cart, facing the aisle, with one hand on its handle.",
        "Their hand is obscured in frame 4, so releasing or moving the cart cannot be established.",
        "In frames 5 and 6, the person in blue sets the box on the table and steps back.",
        "No selected frame shows the box contents or supports a conclusion about either person's intent.",
    ])
    assert 500 < len(account) < 1800
    notice = configured_target_notice({"scene_understanding": account, "summary": "Two people handle a box and cart.",
        "camera_id": "camera-1", "frame_seq": 1, "observed_at": "2026-10-27T20:00:00Z", "source_profile": "bundled_demo"}, {})
    state = operator_state(run_id="run-1", config={}, report={"alerts": [notice["payload"]]},
        latest_frame={}, monitoring={}, supplemental_events=[], preview_status="live", preview_warning="")
    published = []
    class Store:
        def publish_result(self, record_id, activity, **kwargs):
            published.append(activity)
    service = cctv_web_ui.CCTVWebUIService(run_id="run-1", run_dir=tmp_path, config={}, preview_stream=StubPreview())
    service.attach_activity_store(Store())
    service.sync_mcp_activity(state)
    assert len(published) == 1
    assert account in published[0]["message"]
    assert "2026-10-27T20:00:00Z" in published[0]["message"]
    assert "Recorded demo playback" in published[0]["message"]
    assert published[0]["requires_review"] is True


def test_mcp_sidecar_uses_physical_workflow_run_not_submission_label(monkeypatch, tmp_path):
    monkeypatch.delenv("MN_RUN_DIR", raising=False)
    monkeypatch.setenv("MN_RUNS_ROOT", str(tmp_path))
    monkeypatch.setenv("MN_RUN_ID", "submission-label")
    monkeypatch.setenv("MN_WORKFLOW_RUN_ID", "physical-run")
    assert cctv_operator_mcp.configured_run_dir() == tmp_path / "physical-run"
    assert cctv_operator_mcp.configured_run_id() == "physical-run"
    assert cctv_operator_mcp.configured_execution_id() == "submission-label"
    monkeypatch.delenv("MN_RUN_ID")
    with pytest.raises(RuntimeError, match="execution identity"):
        cctv_operator_mcp.configured_execution_id()


def test_mcp_service_uses_one_runtime_allocated_port(monkeypatch, tmp_path):
    execution = json.loads((ROOT / "cctv_operator/execution.json").read_text())
    node = next(node for node in execution["agents"]["extra_nodes"] if node["node_id"] == "cctv_operator_mcp")
    assert node["resources"]["ports"][0]["port"] == "auto"
    assert node["services"][0]["port"] == "${env.MN_PORT_CCTV_OPERATOR_MCP}"
    assert node["services"][0]["checks"][0]["port"] == "${service.port}"
    monkeypatch.setattr(cctv_operator_mcp, "await_endpoint", lambda *a: {
        "url": "http://127.0.0.1:49100", "run_id": "run-1", "token": "private-token",
    })
    monkeypatch.setattr(cctv_operator_mcp, "configured_run_dir", lambda: tmp_path)
    monkeypatch.setenv("MN_RUN_ID", "submission-label")
    monkeypatch.setenv("MN_WORKFLOW_RUN_ID", "run-1")
    seen = []
    monkeypatch.setattr(cctv_operator_mcp, "serve_mcp_proxy", lambda endpoint, **kw: seen.append(kw["port"]))
    monkeypatch.setattr(cctv_operator_mcp.signal, "signal", lambda *a: None)
    for port in (49101, 49102):
        monkeypatch.setenv("MN_PORT_CCTV_OPERATOR_MCP", str(port))
        assert cctv_operator_mcp.main() == 0
    assert seen == [49101, 49102]
    monkeypatch.delenv("MN_PORT_CCTV_OPERATOR_MCP")
    with pytest.raises(RuntimeError, match="runtime-assigned port"):
        cctv_operator_mcp.main()
