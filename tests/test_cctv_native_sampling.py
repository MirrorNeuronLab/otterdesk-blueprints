"""Real compiled sampler with synthetic frame bytes and no resident listener."""

from dataclasses import replace
import importlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from mn_live_video_analysis_skill import write_frame_batch
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_publication_files import deliver_files
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


@pytest.fixture
def sampler(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    module = importlib.import_module("domain.sampling")
    package = read_blueprint(ROOT)
    config = resolve_config(package)
    compiled = compile_blueprint(package, config).manifest
    node = next(row for row in compiled["agents"]["nodes"] if row["node_id"] == "adaptive_frame_sampler")
    assert node["config"]["command"] == ["python3", "-m", "mn_sdk.step_runtime"]
    options = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    descriptor = tmp_path / "runtime.json"
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, config)))
    state_file = tmp_path / "state.json"
    state_file.write_text("{}")
    store = CommittedJsonStore(tmp_path / "run")
    context = StepContext(step_id="adaptively_sample_video", job_id="camera-job", run_id="camera-run",
        agent_id="adaptive_frame_sampler", config=config.data, environment={
            "MN_RUN_DIR": str(store.run_dir), "MN_CONTEXT_FILE": str(state_file),
            "MN_BLOCK_EVENT_PROTOCOL": "mn.block_events/v1",
            "MN_BLOCK_EVENT_PUBLICATION_PROTOCOL": "mn.published_files/v1",
            "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor), "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
        }, message={"envelope": {"message_id": "tick-1", "type": "cctv_operator_sample_due"}, "body": {}})
    calls, waits, sleeps = [], [], []
    result = {"batch": None, "state": {"pending_windows": 0}}
    def claim(root, run_id, **kwargs):
        calls.append({"root": root, "run_id": run_id, **kwargs})
        return result
    monkeypatch.setattr(module, "claim_caption", claim)
    monkeypatch.setattr(module, "await_demo", lambda settings: waits.append(settings))
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 100.0, monotonic=lambda: 0, sleep=sleeps.append))
    return SimpleNamespace(context=context, options=options, state_file=state_file, store=store,
        calls=calls, result=result, waits=waits, sleeps=sleeps, module=module)


def seed_batch(sampler, *, instruction="", revision=0, command_id=""):
    selected = [{"timestamp": 98.0 + index, "content": f"synthetic-frame-{index}".encode(), "score": 0}
        for index in range(2)]
    path, batch = write_frame_batch(sampler.store.run_dir, batch_id="caption-one", trigger="person_gate",
        source={"mode": "stream", "name": "cctv-demo", "uri": "rtsp://camera/live"}, instruction=instruction,
        instruction_revision=revision, candidates=selected, selected=selected,
        schema="otterdesk.cctv_operator.frame_batch.v2", metadata={"camera_id": "cctv-demo", "command_id": command_id})
    message = {key: batch[key] for key in ("batch_id", "trigger", "instruction", "instruction_revision",
        "camera_id", "command_id", "candidate_count", "selected_count")}
    message.update(frame_batch_ref=path.relative_to(sampler.store.run_dir).as_posix(), tick_seq=1)
    sampler.result["batch"] = message
    return path, batch


def state(sampler, result):
    return sampler.store.read(result.event_result["next"])["data"]


def test_native_tick_without_window_keeps_cadence_and_replays_without_claiming(sampler):
    first = run(sampler.context, **sampler.options)
    assert first.event_result["emissions"] == [{"port": "next", "value": {"scheduled_at": 100.0}}]
    assert first.events == []
    assert state(sampler, first)["caption_schedule"] == {"pending_windows": 0}
    assert sampler.calls[0]["run_id"] == "camera-run"
    assert sampler.calls[0]["invocation_id"] == first.event_result["delivery_key"]
    assert sampler.sleeps == [1.0]
    assert not (sampler.store.run_dir / "monitoring_state.json").exists()
    assert run(sampler.context, **sampler.options) == first
    assert len(sampler.calls) == len(sampler.waits) == 1
    assert sampler.sleeps == [1.0]


def test_native_command_uses_live_input_key_and_keeps_only_accepted_state(sampler):
    # Mutable UI files can lag or be modified; they cannot supply native state.
    (sampler.store.run_dir / "monitoring_state.json").write_text(json.dumps({"instruction_revision": 900}))
    context = replace(sampler.context, message={"headers": {"mn.idempotency_key": "operator-42"},
        "envelope": {"message_id": "transport-1"},
        "body": {"instruction": "Watch the left door", "analyze_now": True}})
    first = run(context, **sampler.options)
    monitoring = state(sampler, first)["monitoring"]
    assert monitoring["instruction_revision"] == 1
    assert monitoring["last_command_id"] == "operator-42"
    assert sampler.calls[0]["force"] is True
    assert sampler.calls[0]["monitoring"] == monitoring
    assert sampler.sleeps == [] and first.event_result["emissions"] == []
    assert first.events[0]["type"] == "cctv_operator_attention_updated"
    assert json.loads((sampler.store.run_dir / "monitoring_state.json").read_text())["instruction_revision"] == 900
    assert run(context, **sampler.options) == first
    sampler.state_file.write_text(json.dumps({"agent_state": {
        "version": "mn.block_event_state/v1", "reference": first.event_result["next"]}}))
    second_context = replace(context, message={"envelope": {"message_id": "transport-2"},
        "body": {"clear": True, "analyze_now": False}})
    second = run(second_context, **sampler.options)
    assert state(sampler, second)["monitoring"]["instruction_revision"] == 2
    assert state(sampler, second)["monitoring"]["instruction"] == ""
    assert sampler.calls[-1]["force"] is False


def test_invalid_instruction_is_qualified_without_requesting_forced_analysis(sampler):
    context = replace(sampler.context, message={"envelope": {"message_id": "bad-command"},
        "body": {"instruction": "   "}})
    result = run(context, **sampler.options)
    assert result.events[0]["payload"]["reason"] == "invalid_steering"
    assert state(sampler, result)["monitoring"]["instruction_revision"] == 0
    assert sampler.calls[0]["force"] is False
    assert result.event_result["emissions"] == []


def test_native_window_freezes_evidence_and_publication_repairs_without_source(sampler, monkeypatch):
    path, batch = seed_batch(sampler)
    original_publish = sampler.module.publish_files
    def unavailable(*args, **kwargs):
        raise OSError("synthetic receipt outage")
    monkeypatch.setattr(sampler.module, "publish_files", unavailable)
    with pytest.raises(OSError, match="outage"):
        run(sampler.context, **sampler.options)
    assert not list(sampler.store.run_dir.glob("blocks/*/event-state.json"))
    shutil.rmtree(path.parent)
    monkeypatch.setattr(sampler.module, "publish_files", original_publish)
    first = run(sampler.context, **sampler.options)
    ready, next_tick = first.event_result["emissions"]
    assert ready["port"] == "ready" and next_tick["port"] == "next"
    message = ready["value"]
    assert message["frame_batch_ref"] == sampler.result["batch"]["frame_batch_ref"]
    evidence = sampler.store.read(message["frame_evidence"])
    assert evidence["scope"]["run_id"] == "camera-run"
    assert len(evidence["files"]) == 3
    assert not path.exists()  # The SDK has not published before Core acceptance.
    # Exercise shared delivery as the accepted owner boundary in this unit test.
    owner = SimpleNamespace(check=lambda: None, store=sampler.store, environment={}, agent_id="adaptive_frame_sampler")
    deliver_files(owner, first.publication)
    assert json.loads(path.read_text()) == batch
    assert (path.parent / "frame-01.jpg").read_bytes() == b"synthetic-frame-0"
    assert run(sampler.context, **sampler.options) == first
    assert len(sampler.calls) == len(sampler.sleeps) == 1
    assert "synthetic-frame" not in json.dumps(first.event_result)


def test_lost_resident_reply_reuses_delivery_and_frozen_instruction(sampler, monkeypatch):
    seen = []
    def claim(*_args, **kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            raise TimeoutError("synthetic lost resident reply")
        return sampler.result
    monkeypatch.setattr(sampler.module, "claim_caption", claim)
    context = replace(sampler.context, message={"envelope": {"message_id": "operator-delivery"},
        "body": {"instruction": "Watch the left door"}})
    with pytest.raises(TimeoutError):
        run(context, **sampler.options)
    monkeypatch.setattr(sampler.module.time, "time", lambda: 200.0)
    result = run(context, **sampler.options)
    assert seen[0] == seen[1]
    assert state(sampler, result)["monitoring"]["updated_at"] == 100.0


@pytest.mark.parametrize("value", [{}, {"state": [], "batch": None}, {"state": {}, "batch": {}},
    {"state": {}, "batch": False}, {"state": {}, "batch": None, "unexpected": True}])
def test_invalid_resident_response_never_becomes_an_empty_success(sampler, monkeypatch, value):
    monkeypatch.setattr(sampler.module, "claim_caption", lambda *_args, **_kwargs: value)
    with pytest.raises(ValueError):
        run(sampler.context, **sampler.options)
    assert not list(sampler.store.run_dir.glob("blocks/*/event-state.json"))


@pytest.mark.parametrize("fault", ["escape", "symlink", "hash", "count", "time", "order", "identity", "schema", "oversized"])
def test_invalid_frame_evidence_fails_before_emitting_or_committing_state(sampler, fault, tmp_path):
    path, batch = seed_batch(sampler)
    if fault == "escape":
        batch["selected_frames"][0]["path"] = "../outside.jpg"
    elif fault == "symlink":
        target = path.parent / "frame-01.jpg"
        target.unlink()
        outside = tmp_path / "outside.jpg"
        outside.write_bytes(b"synthetic-frame-0")
        target.symlink_to(outside)
    elif fault == "hash":
        (path.parent / "frame-01.jpg").write_bytes(b"changed")
    elif fault == "count":
        batch["selected_count"] = sampler.result["batch"]["selected_count"] = 3
    elif fault == "time":
        batch["selected_frames"][0]["timestamp"] = float("nan")
    elif fault == "order":
        batch["selected_frames"][0]["timestamp"] = 200.0
    elif fault == "identity":
        sampler.result["batch"]["frame_batch_ref"] = "other.json"
    elif fault == "schema":
        batch["schema"] = "unknown"
    else:
        batch["selected_frames"] *= 20
    path.write_text(json.dumps(batch))
    with pytest.raises(ValueError):
        run(sampler.context, **sampler.options)
    assert not list(sampler.store.run_dir.glob("blocks/*/event-state.json"))
    assert not (sampler.store.run_dir / "monitoring_state.json").exists()
