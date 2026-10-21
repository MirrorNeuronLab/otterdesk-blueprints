"""Compiled CT block integration; only the external native model call is replaced."""

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_blueprint_blocks import BlockError
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import (
    CommittedArtifactConflict,
    CommittedJsonStore,
)

ROOT = Path(__file__).resolve().parents[1] / "ct_reader"


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    package = read_blueprint(ROOT)
    config = resolve_config(package)
    compiled = compile_blueprint(package, config).manifest
    descriptor = tmp_path / "worker-manifest.json"
    descriptor.write_text(
        json.dumps(resolved_worker_descriptor(package, compiled, config))
    )
    node = next(
        n
        for n in compiled["agents"]["nodes"]
        if n.get("config", {}).get("environment", {}).get("MN_WORKFLOW_STEP_HANDLER")
        == "mn_sdk.integrations.block_worker"
    )
    parameters = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    environment = {
        "MN_RUN_DIR": str(tmp_path / "run"),
        "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
        "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    scan = tmp_path / "scan.nii.gz"
    scan.write_bytes(b"synthetic-injected-volume")
    inputs = {"ct_file": str(scan), "region": "chest", "prompt": "Research report"}
    calls = []

    def request(*args, **options):
        calls.append((args, options))
        return {
            "answer": "Synthetic model output for contract testing.",
            "research_only": True,
            "model_revision": "pinned",
        }

    monkeypatch.setattr(
        "mn_sdk.integrations.block_native.runtime_model_json_request", request
    )

    def execute(selected=None):
        context = StepContext(
            step_id="read_ct_volume",
            agent_id=node["node_id"],
            run_id="ct-run",
            idempotency_key="ct-run/read_ct_volume",
            config=config.data,
            environment=environment,
            message={"body": {"step_input": inputs if selected is None else selected}},
        )
        return run(context, **parameters)

    return SimpleNamespace(
        execute=execute,
        store=CommittedJsonStore(tmp_path / "run"),
        calls=calls,
        inputs=inputs,
        scan=scan,
        source=b"synthetic-injected-volume",
    )


def test_ct_compiled_worker_dispatches_exact_native_model_and_publishes_bounded_output(
    worker,
):
    first = worker.execute()
    args, options = worker.calls[0]
    assert args == (
        "inference",
        "nv-reason-ct:0.1.1",
        "/ct",
        {
            "volume_base64": base64.b64encode(worker.source).decode(),
            "region": "chest",
            "prompt": "Research report",
        },
    )
    assert (
        options["provider"] == "docker_model_runner" and options["backend"] == "docker"
    )
    assert options["model_spec"]["protocol"] == "http_json"
    assert options["num_retries"] == 0 and options["timeout_seconds"] == 600
    result = worker.store.read(first.outputs["result"])
    saved = worker.store.read(result["report"])
    assert (
        saved["schema"] == "mn.ct.research_report.v1" and saved["research_only"] is True
    )
    assert saved["input_sha256"] == hashlib.sha256(worker.source).hexdigest()
    assert saved["model_revision"] == "pinned" and len(result["artifacts"]) == 2
    assert "Not for real diagnosis" in worker.store.path("report.md").read_text()
    assert len(json.dumps(first.outputs).encode()) < 2048
    assert "Synthetic model output" not in json.dumps(first.outputs)
    worker.scan.write_bytes(b"changed local file after capture")
    assert worker.execute() == first and len(worker.calls) == 1
    with pytest.raises(CommittedArtifactConflict):
        worker.execute({**worker.inputs, "region": "abdomen"})


def test_ct_interrupted_markdown_publication_recovers_without_repeating_inference(
    worker, monkeypatch
):
    original = CommittedJsonStore.commit_bytes

    def interrupted(store, path, encoded, **options):
        if str(path) == "report.md":
            raise OSError("simulated interruption before Markdown commit")
        return original(store, path, encoded, **options)

    with monkeypatch.context() as patch:
        patch.setattr(CommittedJsonStore, "commit_bytes", interrupted)
        with pytest.raises(OSError):
            worker.execute()
    assert worker.store.path("final_artifact.json").exists()
    assert not worker.store.path("report.md").exists()
    worker.scan.write_bytes(b"changed local file after capture")
    result = worker.store.read(worker.execute().outputs["result"])
    assert (
        worker.store.read(result["report"])["input_sha256"]
        == hashlib.sha256(worker.source).hexdigest()
    )
    assert worker.store.path("report.md").exists() and len(worker.calls) == 1


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"answer": "", "research_only": True},
        {"answer": "Invented clinical claim.", "research_only": False},
        {"answer": "Answer", "research_only": True},
    ],
)
def test_invalid_native_response_never_publishes_or_repeats_inference(
    worker, monkeypatch, result
):
    def request(*args, **options):
        worker.calls.append(args)
        return result

    monkeypatch.setattr(
        "mn_sdk.integrations.block_native.runtime_model_json_request", request
    )
    for _ in range(2):
        with pytest.raises(BlockError) as error:
            worker.execute()
        assert error.value.code == "invalid_native_result"
    assert len(worker.calls) == 1
    assert not worker.store.path("final_artifact.json").exists()


def test_unknown_ct_dispatch_remains_blocked_without_a_second_model_request(
    worker, monkeypatch
):
    def lost(*args, **options):
        worker.calls.append(args)
        raise TimeoutError("response lost")

    monkeypatch.setattr(
        "mn_sdk.integrations.block_native.runtime_model_json_request", lost
    )
    with pytest.raises(TimeoutError):
        worker.execute()
    with pytest.raises(BlockError) as error:
        worker.execute()
    assert error.value.code == "outcome_unknown" and len(worker.calls) == 1
    assert not worker.store.path("final_artifact.json").exists()


@pytest.mark.parametrize(
    "fault", ["empty", "size", "relative", "symlink", "region", "prompt"]
)
def test_ct_invalid_input_fails_before_model_dispatch(worker, monkeypatch, fault):
    import domain.native_inference as native

    inputs = dict(worker.inputs)
    if fault == "empty":
        worker.scan.write_bytes(b"")
    elif fault == "size":
        monkeypatch.setattr(native, "MAX_CT_BYTES", 8)
    elif fault == "relative":
        inputs["ct_file"] = "scan.nii"
    elif fault == "symlink":
        alias = worker.scan.with_name("alias.nii")
        alias.symlink_to(worker.scan)
        inputs["ct_file"] = str(alias)
    elif fault == "region":
        inputs["region"] = "head"
    else:
        inputs["prompt"] = "?" * 2001
    with pytest.raises((ValueError, BlockError)):
        worker.execute(inputs)
    assert worker.calls == [] and not worker.store.path("final_artifact.json").exists()


def test_ct_completed_replay_verifies_published_report_bytes(worker):
    worker.execute()
    worker.store.path("report.md").write_text("corrupt saved report")
    with pytest.raises(RuntimeError):
        worker.execute()
    assert len(worker.calls) == 1
