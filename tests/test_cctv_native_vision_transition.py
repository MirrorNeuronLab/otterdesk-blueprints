"""Catalog-declared native camera policies through the real block engine."""

from copy import deepcopy
import importlib
import json
from pathlib import Path

import pytest
from mn_blueprint_blocks import BlockError
from mn_blueprint_blocks.testing import BlockHarness
from mn_live_video_analysis_skill import write_frame_batch
from mn_sdk.blueprints import blueprint_definition, read_blueprint
from mn_sdk.integrations import block_model_request

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"
SCOPE = {"job_id": "camera-job", "run_id": "camera-run"}
CONFIG = {"text_memory": {"enabled": False}, "site": {"profile": "custom"},
    "video_source": {"mode": "stream", "uri": "rtsp://camera.example/live", "camera_id": "camera"}}
BLOCKS = json.loads((ROOT / "extensions/blocks.json").read_text())
VISION = BLOCKS["events"]["visual_detector"]
REPORT = BLOCKS["events"]["report_writer"]


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    vision = importlib.import_module("domain.vision")
    report = importlib.import_module("domain.report_publication")
    evidence = importlib.import_module("domain.frame_evidence")
    schedule = importlib.import_module("domain.caption_schedule")
    h = BlockHarness(tmp_path / "run")
    descriptor = tmp_path / "runtime.json"
    descriptor.write_text(json.dumps(blueprint_definition(read_blueprint(ROOT))))
    environment = {"MN_BLUEPRINT_MANIFEST_PATH": str(descriptor)}
    def media(prompt, frames, *, media_format):
        assert frames and media_format == "video_url"
        return [{"type": "text", "text": prompt}, {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,dmlkZW8="}}]
    monkeypatch.setattr(vision.vision_model, "model_user_content", media)
    def acknowledge(root, run_id, batch_id, *, status):
        assert run_id == SCOPE["run_id"]
        schedule.complete_caption(root, batch_id, status=status)
    monkeypatch.setattr(vision, "acknowledge_caption", acknowledge)
    calls = []
    account = {"detected_target": False, "confidence": .9, "summary": "A cart remains parked.",
        "scene_understanding": "A cart remains beside the aisle.", "risk_predictions": [], "uncertainties": []}
    def client(*args, **options):
        calls.append((args, options))
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(account)}}]}
    monkeypatch.setattr(block_model_request, "runtime_model_json_request", client)
    options = {**SCOPE, "config": CONFIG, "environment": environment}
    def seed(name="one", sequence=1):
        selected = [{"timestamp": 100.0 + sequence, "content": b"\xff\xd8synthetic frame\xff\xd9"}]
        path, batch = write_frame_batch(h.store.run_dir, batch_id="caption-" + name, trigger="person_gate",
            source={"mode": "stream", "uri": "rtsp://camera.example/live", "name": "camera"},
            instruction_revision=0, candidates=selected, selected=selected, schema="otterdesk.cctv_operator.frame_batch.v2",
            metadata={"camera_id": "camera", "command_id": "", "candidate_gate": {"detector": "RF-DETR", "condition": "person", "confirmed": True}})
        message = {key: batch[key] for key in ("batch_id", "trigger", "instruction", "instruction_revision", "camera_id", "command_id", "candidate_count", "selected_count")}
        message.update(frame_batch_ref=path.relative_to(h.store.run_dir).as_posix(), tick_seq=sequence)
        block = h.context(invocation_id="sample-" + name, agent_id="adaptive_frame_sampler", **options)
        message["frame_evidence"] = evidence.capture_batch(block, message, max_frames=10)
        return message
    def invoke(instance, payload, identifier, *, state=None):
        agent = "visual_detector" if instance is VISION else "report_writer"
        hook = vision.process if instance is VISION else report.process
        return h.value(h.run(instance, {"payload": payload, "input_key": identifier}, invocation_id=identifier,
            agent_id=agent, hooks={"process": hook}, resources={"event_state": state}, **options))
    return h, vision, report, seed, invoke, calls, account


@pytest.mark.parametrize("normal_stop_wrapper", [False, True])
def test_native_vision_to_report_replays_one_model_request_and_no_early_publication(native, monkeypatch, normal_stop_wrapper):
    h, _vision, _report, seed, invoke, calls, _account = native
    if normal_stop_wrapper:
        model = block_model_request.runtime_model_json_request
        def wrapped(*args, **options):
            result = model(*args, **options)
            message = result["choices"][0]["message"]
            message["content"] = "<think>Private reasoning</think><answer>```json\n" + message["content"] + "\n```"
            return result
        monkeypatch.setattr(block_model_request, "runtime_model_json_request", wrapped)
    payload = seed()
    first = invoke(VISION, payload, "vision-1")
    state = h.store.read(first["next"])["data"]
    assert state["frames_seen"] == 1 and state["detections"] == 0
    assert state["last_observation"]["scene_understanding"] == "A cart remains beside the aisle."
    assert first["emissions"][0]["port"] == "observed"
    assert not (h.store.run_dir / "latest_analyzed_frame.jpg").exists()
    assert json.loads((h.store.run_dir / "caption_completions/caption-one.json").read_text())["status"] == "ok"
    assert invoke(VISION, payload, "vision-1") == first
    report = invoke(REPORT, first["emissions"][0]["value"], "report-1")
    saved = json.loads(h.store.read_bytes(h.store.read(report["next"])["data"]["report"]))
    assert h.store.read(report["next"])["data"]["report"] == report["outputs"]["published_files"]["files"]["cctv_report.json"]
    assert saved["frames_analyzed"] == 1 and len(saved["observations"]) == 1
    assert saved["observations"][0]["scene_understanding"] == "A cart remains beside the aisle."
    assert not (h.store.run_dir / "cctv_report.json").exists()
    assert invoke(REPORT, first["emissions"][0]["value"], "report-1") == report
    assert len(calls) == 1 and calls[0][1]["num_retries"] == 0


def test_native_cumulative_report_uses_accepted_history_and_rejects_tampering(native):
    h, _vision, _report, seed, invoke, calls, _account = native
    first = invoke(VISION, seed(), "vision-1")
    report = invoke(REPORT, first["emissions"][0]["value"], "report-1")
    second = invoke(VISION, seed("two", 2), "vision-2", state=first["next"])
    report2 = invoke(REPORT, second["emissions"][0]["value"], "report-2", state=report["next"])
    ref = h.store.read(report2["next"])["data"]["report"]
    saved = json.loads(h.store.read_bytes(ref))
    assert saved["frames_analyzed"] == 2 and [item["frame_seq"] for item in saved["observations"]] == [1, 2]
    assert len(calls) == 2
    h.store.path(ref["path"]).write_bytes(b"changed history")
    with pytest.raises(RuntimeError, match="mismatch"):
        invoke(REPORT, second["emissions"][0]["value"], "report-2", state=report["next"])
    assert len(calls) == 2


def test_unknown_model_outcome_keeps_caption_admission_stalled(native, monkeypatch):
    h, _vision, _report, seed, invoke, calls, _account = native
    def interrupted(*args, **options):
        calls.append((args, options))
        raise TimeoutError("synthetic uncertain inference")
    monkeypatch.setattr(block_model_request, "runtime_model_json_request", interrupted)
    payload = seed()
    with pytest.raises(TimeoutError):
        invoke(VISION, payload, "vision-unknown")
    with pytest.raises(BlockError) as failure:
        invoke(VISION, payload, "vision-unknown")
    assert failure.value.code == "outcome_unknown"
    assert len(calls) == 1
    assert not (h.store.run_dir / "caption_completions").exists()
    assert not list(h.store.run_dir.glob("blocks/*/event-state.json"))


def test_known_invalid_response_is_qualified_and_releases_only_the_known_model_slot(native):
    h, _vision, _report, seed, invoke, calls, account = native
    account.pop("scene_understanding")
    result = invoke(VISION, seed(), "vision-invalid")
    state = h.store.read(result["next"])["data"]
    assert state["frames_seen"] == 0 and state["last_error"]
    assert any(event["type"] == "cctv_operator_frame_analysis_failed" for event in result["events"])
    assert not any(event["type"] == "cctv_operator_frame_observed" for event in result["events"])
    assert json.loads((h.store.run_dir / "caption_completions/caption-one.json").read_text())["status"] == "error"
    assert len(calls) == 1


def test_vision_publication_repair_never_repeats_inference_or_increments_state(native, monkeypatch):
    h, vision, _report, seed, invoke, calls, _account = native
    payload = seed()
    original = vision.publish_files
    def unavailable(*_args, **_options):
        raise OSError("synthetic publication outage")
    monkeypatch.setattr(vision, "publish_files", unavailable)
    with pytest.raises(OSError, match="outage"):
        invoke(VISION, payload, "vision-repair")
    assert len(calls) == 1
    monkeypatch.setattr(vision, "publish_files", original)
    result = invoke(VISION, payload, "vision-repair")
    assert h.store.read(result["next"])["data"]["frames_seen"] == 1 and len(calls) == 1
    metrics = vision.Benchmarks(h.store.run_dir, CONFIG).summary()
    assert sum(stage["ok"] for stage in metrics["stages"] if stage["stage"] == "caption.inference") == 1


def test_lost_completion_ack_retries_the_same_batch_without_another_model_call(native, monkeypatch):
    h, vision, _report, seed, invoke, calls, _account = native
    original = vision.acknowledge_caption
    acknowledgements = []
    def lost_reply(root, run_id, batch_id, *, status):
        original(root, run_id, batch_id, status=status)
        acknowledgements.append((batch_id, status))
        if len(acknowledgements) == 1:
            raise TimeoutError("synthetic lost completion acknowledgement")
    monkeypatch.setattr(vision, "acknowledge_caption", lost_reply)
    payload = seed()
    with pytest.raises(TimeoutError):
        invoke(VISION, payload, "vision-ack")
    first = (h.store.run_dir / "caption_completions/caption-one.json").read_bytes()
    result = invoke(VISION, payload, "vision-ack")
    assert len(calls) == 1 and h.store.read(result["next"])["data"]["frames_seen"] == 1
    assert acknowledgements == [("caption-one", "ok"), ("caption-one", "ok")]
    assert (h.store.run_dir / "caption_completions/caption-one.json").read_bytes() == first


def test_duplicate_admitted_window_never_repeats_model_or_report_emission(native):
    _h, _vision, _report, seed, invoke, calls, _account = native
    payload = seed()
    first = invoke(VISION, payload, "vision-1")
    duplicate = invoke(VISION, payload, "vision-duplicate", state=first["next"])
    assert duplicate["events"] == [] and duplicate["emissions"] == []
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["scope", "kind", "schema"])
def test_report_rejects_foreign_observation_authority_before_publication(native, fault):
    h, _vision, _report, seed, invoke, _calls, _account = native
    result = invoke(VISION, seed(), "vision-1")
    ref = result["emissions"][0]["value"]["observation"]
    record = deepcopy(h.store.read(ref))
    if fault == "scope":
        record["scope"]["run_id"] = "another-run"
    elif fault == "schema":
        record["schema"] = "unknown"
    changed = h.store.commit("foreign-observation.json", record, kind="foreign" if fault == "kind" else "cctv_observation")
    with pytest.raises(ValueError):
        invoke(REPORT, {"observation": changed.to_dict()}, "report-invalid")
    assert not (h.store.run_dir / "cctv_report.json").exists()
