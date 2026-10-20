"""Real block/listener lifecycle with synthetic camera and detector boundaries."""

import importlib
import json
from pathlib import Path
import shutil

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.integrations.block_auxiliary import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


@pytest.mark.parametrize("failure", [None, "monitor_start", "first_frame", "health"])
def test_camera_service_block_owns_real_listeners_and_cleans_partial_start(
    tmp_path, monkeypatch, failure
):
    bundle = tmp_path / "blueprint"
    shutil.copytree(ROOT, bundle, ignore=shutil.ignore_patterns("__pycache__"))
    extension = bundle / "extensions/blocks.json"
    value = json.loads(extension.read_text())
    # Bound only this offline fixture; production remains manually stopped.
    value["services"]["cctv_web_ui"]["config"].update(max_cycles=2, interval_seconds=0)
    extension.write_text(json.dumps(value))
    config_path = bundle / "config/default.json"
    config = json.loads(config_path.read_text())
    config["video_source"]["profile"] = "external"
    config["web_ui"]["service"].update(host="127.0.0.1", port=0)
    config_path.write_text(json.dumps(config))
    monkeypatch.syspath_prepend(str(bundle / "payloads"))
    ui = importlib.import_module("services.cctv_web_ui")
    lifecycle = importlib.import_module("domain.live_service")
    previews, private, servers = [], [], []

    class Preview:
        enabled = True
        stopped = False

        def snapshot(self):
            return {"status": "live", "warning": ""}

        def wait_for_first_frame(self):
            return failure != "first_frame"

        def stop(self):
            self.stopped = True

    def preview(_settings):
        result = Preview()
        previews.append(result)
        return result

    def monitor(self):
        if failure == "monitor_start":
            raise RuntimeError("injected monitor startup failure")

    original_mcp, original_server = ui.start_operator_mcp_server, ui.CCTVWebUIServer

    def start_mcp(*args, **kwargs):
        result = original_mcp(*args, **kwargs)
        private.append(result)
        return result

    def web_server(*args, **kwargs):
        result = original_server(*args, **kwargs)
        servers.append(result)
        return result

    monkeypatch.setattr(ui, "CUDAMJPEGPreview", preview)
    monkeypatch.setattr(ui.CCTVWebUIService, "start_monitor", monitor)
    monkeypatch.setattr(ui, "start_operator_mcp_server", start_mcp)
    monkeypatch.setattr(ui, "CCTVWebUIServer", web_server)
    if failure == "health":
        original_health = lifecycle.health
        checks = []

        def health(block, inputs):
            checks.append(True)
            return original_health(block, inputs) if len(checks) == 1 else False

        monkeypatch.setattr(lifecycle, "health", health)
    job_data = tmp_path / "jobs/camera-job"
    job_data.mkdir(parents=True)
    output = tmp_path / "runs/camera-run"
    for name, value in {
        "MN_JOB_DATA_DIR": job_data,
        "MN_HOME": tmp_path / "home",
        "MN_RUN_DIR": output,
        "MN_RUN_ID": "camera-run",
        "MN_JOB_ID": "camera-job",
        "MN_JOB_SHARED_STORAGE_ROOT": tmp_path / "shared",
    }.items():
        monkeypatch.setenv(name, str(value))
    for name in (
        "MN_BLUEPRINT_WEB_UI_BASE_URL",
        "MN_WEB_UI_PROXY_HOST",
        "MN_DOCKER_WORKER_CONTAINER_NAME",
        "MN_EXECUTION_NODE",
    ):
        monkeypatch.delenv(name, raising=False)
    compiled = compile_blueprint(read_blueprint(bundle)).manifest
    descriptor = tmp_path / "runtime.json"
    descriptor.write_text(json.dumps(compiled))
    node = next(n for n in compiled["agents"]["nodes"] if n["node_id"] == "cctv_web_ui")
    options = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    context = StepContext(
        step_id="",
        job_id="camera-job",
        run_id="camera-run",
        agent_id="cctv_web_ui",
        config=config,
        message={"envelope": {"message_id": "camera-delivery"}},
        environment={
            "MN_RUN_DIR": str(output),
            "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
            "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
        },
    )
    if failure:
        with pytest.raises((RuntimeError, ValueError)):
            run(context, **options)
        assert not list(output.glob("blocks/*/service/terminal.json"))
    else:
        result = run(context, **options)
        assert (
            CommittedJsonStore(output).read(result.outputs["result"])[
                "cycles_completed"
            ]
            == 2
        )
        assert run(context, **options) == result
        assert len(private) == 1  # A completed delivery never starts another camera.
    assert private and all(
        not worker.is_alive() for managed in private for worker in managed.threads
    )
    assert previews and all(item.stopped for item in previews)
    assert all(server._server.socket.fileno() == -1 for server in servers)
    if failure not in {"monitor_start", "first_frame"}:
        assert json.loads((job_data / "web_ui.json").read_text())["status"] == "stopped"
