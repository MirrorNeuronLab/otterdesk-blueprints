"""OpenShell provisioning must build its image before the Docker worker stage."""

import json
from pathlib import Path
from unittest.mock import patch


def test_reviewer_builds_explicit_sandbox_context_before_provisioning(tmp_path, monkeypatch):
    from mn_cli.libs.run_cmds import openshell

    root = Path(__file__).resolve().parents[2] / "software_architecture_advisor"
    execution = json.loads((root / "execution.json").read_text())
    config = next(group["with"] for group in execution["workers"]["groups"]
                  if group["with"].get("runner_module") == "MirrorNeuron.Runner.OpenShell")
    context = root / "payloads" / config["custom_openshell_image"]
    assert "iproute2" in (context / "Dockerfile").read_text()
    assert config["environment"]["PYTHONPATH"] == "."
    order = []

    def build(source, node):
        assert source == context.resolve()
        order.append("build")
        return "openshell/sandbox-from:verified"

    def provision(bundle, prepared, **kwargs):
        assert prepared["from"] == "openshell/sandbox-from:verified"
        assert prepared["runner_module"] == "MirrorNeuron.Runner.OpenShell"
        order.append("provision")

    with patch.object(openshell, "_openshell_executable", return_value="openshell"), \
         patch.object(openshell, "_build_openshell_from_image", side_effect=build), \
         patch.object(openshell, "_prepare_openshell_shared_sandbox", side_effect=provision), \
         patch.object(openshell, "_record_openshell_native_resource"):
        openshell._prepare_openshell_custom_images(
            root, {"flow": {"nodes": [{"node_id": "review", "config": config}]}},
            shared_sandbox_job_id="test-job",
        )
    assert order == ["build", "provision"]


def test_docker_worker_accepts_sdk_skill_preparation(tmp_path):
    from mn_sdk.skill_worker_preparation import prepare_skill_worker_assets

    root = Path(__file__).resolve().parents[2] / "software_architecture_advisor"
    execution = json.loads((root / "execution.json").read_text())
    config = dict(next(group["with"] for group in execution["workers"]["groups"]
                       if group["uses"] == "mn-agents.worker.python_docker@1"))
    config["runner_module"] = "MirrorNeuron.Runner.DockerWorker"
    manifest = {
        "skill_dependencies": [{"name": "fixture-skill", "version": "1.0", "type": "pip", "source": "gar"}],
        "agents": {"nodes": [{"node_id": "capture", "config": config}]},
    }
    payloads = {config["dockerfile"]: (root / "payloads" / config["dockerfile"]).read_bytes()}
    (tmp_path / "fixture_hook.py").write_text(
        "def prepare(request):\n"
        "    return {'version': 1, 'dockerfile': 'RUN echo skill-prepared'}\n"
    )

    class Cluster:
        def get_system_summary(self):
            return {"nodes": [{"name": "worker", "hardware": {"cpu": {"architecture": "aarch64"}}}]}

    prepare_skill_worker_assets(
        manifest, payloads, cluster_client=Cluster(),
        env={"MN_SELECTED_RUNTIME_NODE": "worker"},
        resolver=lambda *_: ("fixture_hook:prepare", tmp_path),
    )
    prepared = payloads[config["dockerfile"]].decode()
    assert prepared.startswith("FROM python:3.11-slim-bookworm\n")
    assert "RUN echo skill-prepared" in prepared
