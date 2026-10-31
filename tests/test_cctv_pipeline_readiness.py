"""Cold model preparation must not freeze old goals or misreport coverage."""

import io
import threading
import time
from types import SimpleNamespace

from PIL import Image

from cctv_operator.payloads.domain import live_monitor, scene_model
from cctv_operator.payloads.domain.dashboard import operator_state
from cctv_operator.payloads.domain.pipeline_status import pipeline_status


def image():
    output = io.BytesIO()
    Image.new("RGB", (64, 32)).save(output, "JPEG")
    return output.getvalue()


def monitor(tmp_path):
    return live_monitor.LiveMonitor(tmp_path, "camera-run",
        {"sampling": {"pre_roll_seconds": 1.5, "post_roll_seconds": .5}},
        SimpleNamespace(), None, detector=SimpleNamespace(variant="RF-DETR"))


def test_cold_preparation_keeps_the_goal_live_and_admits_only_fresh_evidence(tmp_path, monkeypatch):
    worker = monitor(tmp_path)
    preparing, release = threading.Event(), threading.Event()

    def prepare(config):
        preparing.set()
        assert release.wait(5)

    monkeypatch.setattr(live_monitor, "prepare_scene_model", prepare)
    thread = threading.Thread(target=worker._prepare_scene_model)
    thread.start()
    try:
        assert preparing.wait(5)
        now = time.time()
        first = {"instruction": "Watch the door", "instruction_revision": 1}
        worker.caption_schedule.person_sample(now - 100, confirmed=True, episode=1)
        worker.caption_schedule.capture(1, now - 99, image(), first)
        request = {"operation": "claim_caption", "monitoring": first, "invocation_id": "sample-1"}
        pending = worker.request(request)
        assert pending["batch"] is None and pending["state"]["inflight"] is None

        # Steering during preparation remains live; no old command has claimed
        # a model slot or consumed its physical invocation identity.
        latest = {"instruction": "Watch for uncovered heads", "instruction_revision": 2}
        worker.caption_schedule.person_sample(now - 1, confirmed=True, episode=2)
        worker.caption_schedule.capture(2, now, image(), latest)
        assert worker.request({**request, "monitoring": latest})["batch"] is None
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        accepted = worker.request({**request, "monitoring": latest})["batch"]
        assert accepted["instruction"] == latest["instruction"]
        assert accepted["instruction_revision"] == 2
        import json
        batch = json.loads((tmp_path / accepted["frame_batch_ref"]).read_text())
        assert all(frame["timestamp"] >= now - 2 for frame in batch["selected_frames"])
        measured = next(row for row in worker.benchmarks.summary()["stages"] if row["stage"] == "caption.model_prepare")
        assert measured["ok"] == 1 and measured["errors"] == 0
    finally:
        release.set()
        thread.join(5)


def test_failed_or_stopped_preparation_never_opens_admission(tmp_path, monkeypatch):
    worker = monitor(tmp_path)
    def fail(_config):
        raise RuntimeError("Model preparation failed")
    monkeypatch.setattr(live_monitor, "prepare_scene_model", fail)
    worker._supervise("scene-model", worker._prepare_scene_model)
    assert worker.status["scene_model"] == "failed"
    pipeline, warning = pipeline_status(worker.status, worker.caption_schedule.snapshot())
    assert pipeline["captions"]["summary"] == "Scene analysis preparation failed."
    assert "Couldn't prepare scene analysis" in warning
    assert worker.request({"operation": "claim_caption"})["batch"] is None

    worker.stop_event.set()
    monkeypatch.setattr(live_monitor, "prepare_scene_model", lambda _config: None)
    worker._prepare_scene_model()
    assert worker.status["scene_model"] != "ready"


def test_camera_preparation_selects_vision_independently_of_conversation_model(monkeypatch):
    monkeypatch.setenv("MN_LLM_MODEL", "text-model")
    monkeypatch.delenv("MN_VLM_MODEL", raising=False)
    monkeypatch.delenv("MN_VLM_PROVIDER", raising=False)
    monkeypatch.delenv("MN_VLM_BACKEND", raising=False)
    spec = {"id": "vision-model"}
    monkeypatch.setattr(scene_model, "source_manifest", lambda *args, **kwargs: {
        "runtime": {"models": {"vision": {"model": "vision-model", "provider": "docker_model_runner",
            "backend": "nim", "model_spec": spec}}}})
    calls = []
    monkeypatch.setattr(scene_model, "ensure_runtime_model", lambda *args, **kwargs: calls.append((args, kwargs)))
    scene_model.prepare_scene_model({})
    assert calls[0][0] == ("vlm", "vision-model")
    assert calls[0][1]["backend"] == "nim"
    assert calls[0][1]["model_spec"] == spec
    assert calls[0][1]["required_capabilities"] == ["image_input"]


def state(*, analyzed_at="2026-10-30T18:09:51Z", pipeline=None, now=1793383795):
    return operator_state(run_id="run", config={}, report={"observations": [{
        "observed_at": "2026-10-30T18:08:42Z", "analyzed_at": analyzed_at,
        "scene_understanding": "A person is walking.", "summary": "A person is walking."}]},
        latest_frame={}, monitoring={}, supplemental_events=[], preview_status="live",
        preview_warning="", pipeline=pipeline, now=now)


def test_recent_completion_is_not_stale_because_its_camera_frames_are_older():
    result = state()
    assert result["metrics"]["status"] == "Monitoring"
    assert result["metrics"]["last analyzed"] == "2026-10-30T18:09:51Z"
    assert result["metrics"]["last captured"] == "2026-10-30T18:08:42Z"
    assert "delayed" not in result["warning"]
    assert state(now=1793383900)["metrics"]["status"] == "Analysis delayed"


def test_processing_and_preparation_have_separate_health_and_truthful_coverage():
    pipeline = {"person_events": {"scene_model": "ready"}, "captions": {
        "inflight_status": "processing", "skipped_windows": 111, "stale_windows": 2,
        "last_offered_at": 1793383899}}
    result = state(now=1793383900, pipeline=pipeline)
    assert result["metrics"]["status"] == "Monitoring"
    assert result["metrics"]["samples skipped"] == 113
    assert result["metrics"]["last sampled"] == "2026-10-30T18:11:39Z"
    pipeline["captions"]["inflight_status"] = "stalled"
    assert state(pipeline=pipeline)["metrics"]["status"] == "Analysis delayed"
    pipeline["person_events"].update(scene_model="preparing", scene_model_started_at=100)
    projection, _ = pipeline_status(pipeline["person_events"], {}, now=500)
    assert projection["captions"]["summary"] == "Preparing scene analysis (400 s)."
    assert state(pipeline=pipeline)["metrics"]["status"] == "Preparing scene analysis"
