from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
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
SPEC = importlib.util.spec_from_file_location("cctv_web_ui", MODULE_PATH)
assert SPEC and SPEC.loader
cctv_web_ui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cctv_web_ui)
MCP_SPEC = importlib.util.spec_from_file_location(
    "cctv_operator_mcp", SERVICES_DIR / "cctv_operator_mcp.py"
)
assert MCP_SPEC and MCP_SPEC.loader
cctv_operator_mcp = importlib.util.module_from_spec(MCP_SPEC)
MCP_SPEC.loader.exec_module(cctv_operator_mcp)


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
    import cctv_operator_mcp as proxy_module

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
    cctv_web_ui.start_operator_mcp_server(object(), job_id="job-1", run_id="run-1", run_dir=tmp_path)
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


def test_cctv_operator_owns_an_sdk_mcp_activity_exchange(tmp_path: Path):
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
                ]
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
            assert (run_id, input_id) == ("run-1", "steer_monitoring")
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
                "tool": lambda self, name=None, **_kw: lambda fn: self.tools.setdefault(name or fn.__name__, fn) or fn,
                "resource": lambda self, uri, **_kw: lambda fn: self.resources.setdefault(uri, fn) or fn,
            },
        )(),
    )

    status = server.tools["get_operator_status"]()
    assert status["status"] == service.ui_state()["metrics"]["status"]
    assert status["finding"] == "A person is visible near the center of the frame."
    assert status["ready"] is True
    assert status["details"] == [{"label": "Confidence", "value": "92%"}, {"label": "Risk", "value": "low"}]
    assert status["finding"] in status["summary"]
    assert status["observed_at"] in status["summary"]

    activity = server.tools["get_operator_activity"]("0")

    assert set(server.tools) == {
        "acknowledge_operator_notice",
        "get_command_status",
        "get_operator_activity",
        "get_operator_status",
        "set_monitoring_instruction",
        "watch_operator_activity",
    }
    receipt = server.tools["set_monitoring_instruction"](
        "11111111-1111-4111-8111-111111111111",
        "Find foreign objects on the floor.",
        "false",
        "true",
    )
    assert receipt["state"] == "accepted"
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
    command_status = server.tools["get_command_status"](
        "11111111-1111-4111-8111-111111111111"
    )
    assert command_status["state"] == "completed"
    assert command_status["instruction_revision"] == 2
    assert activity["updates"][-1]["payload"] == {
        "schema_version": "mn.mcp.job_activity.v1",
        "event_id": activity["updates"][-1]["record_id"],
        "title": "Target observed",
        "message": "A person is visible near the center of the frame.",
        "occurred_at": "2026-09-08T22:23:39Z",
        "source": "cctv_operator",
        "requires_review": True,
        "details": [{"label": "Confidence", "value": "92%"}, {"label": "Risk", "value": "low"}],
    }


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


def test_mcp_service_uses_one_runtime_allocated_port(monkeypatch, tmp_path):
    execution = json.loads((ROOT / "cctv_operator/execution.json").read_text())
    node = next(node for node in execution["agents"]["extra_nodes"] if node["node_id"] == "cctv_operator_mcp")
    assert node["resources"]["ports"][0]["port"] == "auto"
    assert node["services"][0]["port"] == "${env.MN_PORT_CCTV_OPERATOR_MCP}"
    assert node["services"][0]["checks"][0]["port"] == "${service.port}"
    monkeypatch.setattr(cctv_operator_mcp, "await_endpoint", lambda *a: {"url": "http://127.0.0.1:49100"})
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
