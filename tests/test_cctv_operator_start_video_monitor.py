"""Compiled native CCTV ingress; no camera, GPU, model or live Core required."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext, normalize_result
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


@pytest.fixture
def ingress(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    module = importlib.import_module("domain.monitor_ingress")
    calls = []
    def validate(config):
        calls.append(config)
        return "Approved source validated."
    monkeypatch.setattr(module, "validate_source", validate)
    package = read_blueprint(ROOT)
    config = resolve_config(package)
    compiled = compile_blueprint(package, config).manifest
    node = next(node for node in compiled["agents"]["nodes"] if node["node_id"] == "ingress")
    assert node["config"]["command"] == ["python3", "-m", "mn_sdk.step_runtime"]
    options = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    descriptor = tmp_path / "runtime.json"
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, config)))
    state_file = tmp_path / "core-context.json"
    state_file.write_text("{}")
    store = CommittedJsonStore(tmp_path / "run")
    context = StepContext(step_id="start_video_monitor", job_id="camera-job", run_id="camera-run",
        agent_id="ingress", config=config.data, environment={
            "MN_RUN_DIR": str(store.run_dir), "MN_CONTEXT_FILE": str(state_file),
            "MN_BLOCK_EVENT_PROTOCOL": "mn.block_events/v1",
            "MN_BLOCK_EVENT_PUBLICATION_PROTOCOL": "mn.published_files/v1",
            "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor), "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
        }, message={"envelope": {"message_id": "start-1", "type": "cctv_operator_start"},
            "body": {"stream_id": "demo"}})
    return SimpleNamespace(context=context, options=options, calls=calls, store=store,
        state_file=state_file, module=module)


def test_native_start_validates_once_and_declares_only_its_output_port(ingress):
    first = run(ingress.context, **ingress.options)
    assert first.outputs["stream_session"] == {"status": "ready", "stream_id": "demo"}
    assert first.event_result["emissions"] == [{"port": "start", "value": {"stream_id": "demo"}}]
    assert first.events[0]["type"] == "video_monitor_start"
    assert "complete_step" not in normalize_result(first, ingress.context)
    assert run(ingress.context, **ingress.options) == first
    assert len(ingress.calls) == 1
    state = ingress.store.read(first.event_result["next"])
    assert state["data"]["stream_session"] == first.outputs["stream_session"]


def test_native_steering_keeps_the_ready_session_without_revalidation(ingress):
    first = run(ingress.context, **ingress.options)
    ingress.state_file.write_text(json.dumps({"agent_state": {
        "version": "mn.block_event_state/v1", "reference": first.event_result["next"]}}))
    command = {"instruction": "Watch the left door", "analyze_now": True}
    context = replace(ingress.context, message={
        "envelope": {"message_id": "steer-2", "type": "cctv_operator_steer"}, "body": command})
    second = run(context, **ingress.options)
    assert second.event_result["emissions"] == [{"port": "steer", "value": command}]
    assert second.outputs["stream_session"] == first.outputs["stream_session"]
    assert second.event_result["previous"] == first.event_result["next"]
    assert run(context, **ingress.options) == second
    assert len(ingress.calls) == 1


def test_seed_payload_keeps_its_declared_start_type(ingress):
    context = replace(ingress.context, message={"envelope": {"message_id": "seed-1", "type": "init"},
        "body": {"type": "cctv_operator_start", "payload": {"stream_id": "seed"}}})
    result = run(context, **ingress.options)
    assert result.event_result["emissions"] == [{"port": "start", "value": {"stream_id": "seed"}}]
    assert len(ingress.calls) == 1


def test_unknown_command_fails_before_source_validation(ingress):
    context = replace(ingress.context, message={"envelope": {"message_id": "bad-1", "type": "unknown"}, "body": {}})
    with pytest.raises(ValueError, match="Unsupported"):
        run(context, **ingress.options)
    assert ingress.calls == []
    assert not list(ingress.store.run_dir.glob("blocks/*/event-state.json"))


def test_rejected_source_never_commits_a_ready_session(ingress, monkeypatch):
    def unavailable(_config):
        raise ValueError("Approved camera unavailable")
    monkeypatch.setattr(ingress.module, "validate_source", unavailable)
    with pytest.raises(ValueError, match="unavailable"):
        run(ingress.context, **ingress.options)
    assert not list(ingress.store.run_dir.glob("blocks/*/event-state.json"))


def test_source_policy_is_shared_with_the_submission_validator(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    policy = importlib.import_module("domain.source_validation")
    source = tmp_path / "approved.mp4"
    source.write_bytes(b"synthetic approved fixture")
    config = {"video_source": {"mode": "stream", "profile": "bundled_demo",
        "uri": "rtsp://127.0.0.1:8554/cctv-demo", "demo_file": str(source)}}
    def probe(*_args, **_kwargs):
        pytest.fail("Bundled source must be probed by its resident camera owner")
    monkeypatch.setattr(policy, "probe_stream", probe)
    assert "DockerWorker" in policy.validate_source(config)
    config["video_source"]["mode"] = "folder"
    with pytest.raises(policy.SourceValidationError) as result:
        policy.validate_source(config)
    assert result.value.status == 2
    assert result.value.report["issues"][0]["code"] == "config.invalid_source_mode"
