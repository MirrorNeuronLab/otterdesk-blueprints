"""The reviewer image and policy are prepared through the shared SDK."""

import json
from pathlib import Path
import subprocess


def test_reviewer_builds_explicit_sandbox_context_before_provisioning(tmp_path, monkeypatch):
    from mn_sdk import openshell_native, openshell_preparation
    from mn_sdk.blueprints import blueprint_definition, read_blueprint
    from mn_sdk.submission import prepare_job_submission

    root = Path(__file__).resolve().parents[2] / "software_architecture_advisor"
    definition = blueprint_definition(read_blueprint(root))
    config = next(group["with"] for group in definition["workers"]["groups"]
                  if group["with"].get("runner_module") == "MirrorNeuron.Runner.OpenShell")
    context = root / "payloads" / config["custom_openshell_image"]
    config["environment"]["MN_BLUEPRINT_CONFIG_JSON"] = (root / "config/default.json").read_text()
    assert "iproute2" in (context / "Dockerfile").read_text()
    assert config["environment"]["PYTHONPATH"] == "."
    commands = []

    def execute(args, **kwargs):
        commands.append(args)
        if args[:2] == ["docker", "build"]:
            assert "iproute2" in (Path(args[-1]) / "Dockerfile").read_text()
        return subprocess.CompletedProcess(args, int(args[1:3] == ["sandbox", "get"]), "", "")

    monkeypatch.setattr(openshell_native.shutil, "which", lambda *_args, **_kw: "/test/bin/openshell")
    monkeypatch.setattr(openshell_preparation, "prepare_openshell", lambda request, **kw:
                        openshell_native.prepare_openshell(request, command_runner=execute, **kw))
    manifest = {"apiVersion": "mn.workflow/v1", "kind": "Workflow", "id": "advisor-review",
                "contract": {}, "runtime": {}, "agents": {"nodes": [{"node_id": "review", "config": config}]}}
    payloads = {file.relative_to(root / "payloads").as_posix(): file.read_bytes()
                for file in context.rglob("*") if file.is_file()}
    env = {"MN_HOME": str(tmp_path), "MN_NODE_NAME": "test-owner", "MN_SYNCTHING_ENABLED": "0",
           "OPENSHELL_GATEWAY_ENDPOINT": "http://127.0.0.1:58080"}
    submission = prepare_job_submission(manifest, payloads, env=env, job_id="test-job",
                                        submission_id="test-submission", run_id="test-run")
    prepared = json.loads(submission.manifest_json)["agents"]["nodes"][0]["config"]
    assert [args[:2] for args in commands] == [
        ["/test/bin/openshell", "sandbox"], ["docker", "build"],
        ["/test/bin/openshell", "sandbox"], ["/test/bin/openshell", "sandbox"],
    ]
    create = commands[-1]
    assert create[create.index("--from") + 1] == prepared["from"] == commands[1][3]
    assert create[create.index("--name") + 1] == prepared["sandbox_name"]


def test_docker_worker_accepts_sdk_skill_preparation(tmp_path):
    from mn_sdk.blueprints import read_blueprint
    from mn_sdk.skill_worker_preparation import prepare_skill_worker_assets

    root = Path(__file__).resolve().parents[2] / "software_architecture_advisor"
    assets = {asset.path for asset in read_blueprint(root).assets}
    dockerfile = (root / "payloads/docker_worker/Dockerfile").read_text()
    for line in dockerfile.splitlines():
        if line.startswith("COPY "):
            source = "payloads/" + line.split()[1]
            assert any(path == source or (source.endswith("/") and path.startswith(source))
                       for path in assets), source
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
    assert prepared.startswith("FROM python:3.12-slim-bookworm\n")
    assert "RUN echo skill-prepared" in prepared


def test_compiled_review_policy_uses_resolved_config_and_ships_to_core():
    from mn_sdk.blueprints import read_blueprint, resolve_config, compile_blueprint
    from mn_sdk.openshell_policy import stage_worker_policies
    from mn_sdk.submission_preparation import lower_manifest_topology_for_runtime_submission
    root = Path(__file__).resolve().parents[2] / 'software_architecture_advisor'
    package = read_blueprint(root)
    manifest = compile_blueprint(package, resolve_config(package)).manifest
    lower_manifest_topology_for_runtime_submission(manifest)
    payloads = {}
    stage_worker_policies(manifest, payloads, bundle_dir=root)
    policy = payloads['openshell_worker/policy.yaml'].decode()
    assert '${config.' not in policy
    assert 'host: "10.0.4.27"' in policy and 'host: "10.0.4.32"' in policy
    assert 'port: 4000' in policy
    assert '/v1/chat/completions' in policy
    assert 'enforcement: enforce' in policy
    assert '${config.' in (root/'payloads/openshell_worker/policy.yaml').read_text()
