"""Execute the compiled native SDK service with real listeners and fake VSS."""

import importlib
import json
from pathlib import Path
import shutil

import httpx
import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.integrations.block_auxiliary import run
from mn_sdk.step_runtime import StepContext

from test_cctv_realtime_protocol import CaptionStream

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


@pytest.mark.parametrize("failure", [None, "health", "model", "proxy"])
def test_native_block_claims_ui_saves_real_protocol_output_and_cleans_listeners(tmp_path, monkeypatch, failure):
    bundle = tmp_path / "blueprint"
    shutil.copytree(ROOT, bundle, ignore=shutil.ignore_patterns("__pycache__"))
    path = bundle / "extensions/blocks.json"
    blocks = json.loads(path.read_text())
    blocks["services"]["camera_operator"]["config"].update(max_cycles=2, interval_seconds=0, startup_timeout_seconds=3)
    path.write_text(json.dumps(blocks))
    config = json.loads((bundle / "config/default.json").read_text())
    config["video_source"]["uri"] = "rtsp://camera/stream"
    config["web_ui"]["service"]["host"] = "127.0.0.1"
    if failure == "proxy":
        config["web_ui"]["service"]["host"] = "0.0.0.0"
    monkeypatch.syspath_prepend(str(bundle / "payloads"))
    native = importlib.import_module("domain.operator_service")
    lifecycle = importlib.import_module("domain.service_lifecycle")
    client_module = importlib.import_module("domain.realtime_client")
    if failure == "proxy":
        monkeypatch.setattr(lifecycle.socket, "gethostbyname", lambda host: "127.0.0.2")
    calls, operators, previews, control_hosts = [], [], [], []

    async def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [] if failure == "model" else [{"id": "Cosmos3-Edge"}]})
        if request.url.path == "/v1/streams/add":
            return httpx.Response(200, json={"results": [{"id": "camera-1"}]})
        if request.method == "POST" and request.url.path == "/v1/generate_captions":
            return httpx.Response(200, stream=CaptionStream())
        return httpx.Response(200, text="ok")

    def client(base_url):
        return client_module.VLMClient(base_url, httpx.AsyncClient(base_url="http://vlm/", transport=httpx.MockTransport(handler)))

    class Preview:
        jpeg = None
        frame_number = 0
        last_frame_at = 0
        def __init__(self):
            self.stopped = False
            previews.append(self)
        def start(self, uri):
            pass
        def status(self):
            return {"connected": False}
        def stop(self):
            self.stopped = True

    original = native.Operator.__init__
    def construct(self, **options):
        original(self, **options)
        operators.append(self)
        control_hosts.append(self.mcp_socket.getsockname()[0])
    monkeypatch.setattr(native.Operator, "__init__", construct)
    monkeypatch.setattr(native, "VLMClient", client)
    monkeypatch.setattr(native, "Preview", Preview)
    if failure == "health":
        original_health = lifecycle.health
        checks = []
        def health(block, inputs):
            checks.append(True)
            return original_health(block, inputs) if len(checks) == 1 else False
        monkeypatch.setattr(lifecycle, "health", health)
    job_data, output = tmp_path / "jobs/job", tmp_path / "runs/run"
    job_data.mkdir(parents=True)
    for name, value in {"MN_JOB_DATA_DIR": job_data, "MN_HOME": tmp_path / "home", "MN_RUN_DIR": output,
                        "MN_RUN_ID": "execution", "MN_WORKFLOW_RUN_ID": "run", "MN_JOB_ID": "job",
                        "MN_JOB_SHARED_STORAGE_ROOT": tmp_path / "shared"}.items():
        monkeypatch.setenv(name, str(value))
    for name in ["MN_PORT_CCTV_OPERATOR_MCP", "MN_PORT_WEB_UI", "MN_EXECUTION_NODE", "MN_BLUEPRINT_WEB_UI_BASE_URL"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("MN_MCP_HOST", raising=False)
    monkeypatch.setenv("MN_MCP_CONTAINER_LOOPBACK_PROXY", "1" if failure == "proxy" else "0")
    compiled = compile_blueprint(read_blueprint(bundle)).manifest
    descriptor = tmp_path / "compiled.json"
    descriptor.write_text(json.dumps(compiled))
    node = next(node for node in compiled["agents"]["nodes"] if node["node_id"] == "camera_operator")
    parameters = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    context = StepContext(step_id="", job_id="job", job_data_dir=str(job_data), run_id="run", agent_id="camera_operator",
                          config=config, message={"envelope": {"message_id": "delivery"}},
                          environment={"MN_RUN_DIR": str(output), "MN_RUN_ID": "execution", "MN_WORKFLOW_RUN_ID": "run",
                                       "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor), "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'})
    if failure in {"health", "model"}:
        with pytest.raises((RuntimeError, ValueError)):
            run(context, **parameters)
    else:
        result = run(context, **parameters)
        assert run(context, **parameters) == result
        assert len(operators) == 1
        assert control_hosts == ["0.0.0.0" if failure == "proxy" else "127.0.0.1"]
        if failure == "proxy":
            handle = json.loads((job_data / "web_ui.json").read_text())
            assert handle["url"].startswith("http://127.0.0.2:")
        report = json.loads((output / "cctv_report.json").read_text())
        assert report["observations"][0]["model"] == "Cosmos3-Edge"
        assert ("DELETE", "/v1/streams/delete/camera-1") in calls
    assert operators and not operators[0].thread.is_alive()
    assert operators[0].web_socket.fileno() == operators[0].mcp_socket.fileno() == -1
    assert previews and all(preview.stopped for preview in previews)
    assert operators[0].store.state("active_request") is None
