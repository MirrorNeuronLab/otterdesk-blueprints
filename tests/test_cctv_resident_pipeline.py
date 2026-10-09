"""CCTV lane isolation, evidence ordering, temporal policy and measured stages."""

import io
import json
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from PIL import Image

from cctv_operator.payloads.domain.benchmarks import Benchmarks
from cctv_operator.payloads.domain.benchmark_replay import accuracy, load_dataset, replay
from cctv_operator.payloads.domain.caption_schedule import CaptionSchedule, complete_caption
from cctv_operator.payloads.domain.live_monitor import LiveMonitor
from cctv_operator.payloads.domain.person_detector import RFDETRPersonDetector, verify_checkpoint
from cctv_operator.payloads.domain.person_events import PersonEpisodes
from cctv_operator.payloads.domain.person_evidence import PersonEvidence
from cctv_operator.payloads.domain.pipeline_status import pipeline_status, person_status_summary


def jpeg(color="black"):
    stream = io.BytesIO()
    Image.new("RGB", (96, 54), color).save(stream, "JPEG")
    return stream.getvalue()


PERSON = {"label": "person", "confidence": .9, "xyxy": [1, 2, 30, 40]}


def test_person_episode_requires_persistence_rearms_after_observed_absence_and_ignores_gaps():
    detector = PersonEpisodes({})
    assert detector.update([PERSON], 10) is None
    event = detector.update([PERSON], 10.2)
    assert event["started_at"] == 10 and event["person_count"] == 1
    assert detector.update([PERSON], 10.4) is None
    # Repeated/out-of-order frames cannot advance persistence.
    assert detector.update([], 10.3) is None
    detector.update([], 11)
    detector.update([], 20)  # gap does not prove absence
    assert detector.state["active"] is True
    detector.update([], 20.2)
    detector.update([], 22.2)
    assert detector.state["active"] is False
    assert detector.update([PERSON], 22.4) is None
    assert detector.update([PERSON], 22.6)["episode"] == 2
    assert detector.update([PERSON], 22.8, revision=1) is None
    assert detector.update([PERSON], 23, revision=1)["episode"] == 3


def gated_capture(schedule, revision, timestamp, content, monitoring, *, episode=1):
    schedule.person_sample(timestamp - schedule.policy.post_roll_seconds, confirmed=True, episode=episode)
    schedule.person_sample(timestamp, confirmed=True, episode=episode)
    schedule.capture(revision, timestamp, content, monitoring)


@pytest.mark.parametrize("instruction", ["", "Person presence", "A blocked corridor", "A missing helmet"])
def test_quiet_frames_and_requested_analysis_cannot_bypass_fixed_person_gate(tmp_path, instruction):
    schedule = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    goal = {"instruction": instruction, "instruction_revision": 1}
    schedule.capture(1, 100, jpeg(), goal)
    assert schedule.claim(goal, force=True, now=101)["batch"] is None
    assert schedule.snapshot()["pending_windows"] == 0
    schedule.person_sample(102, confirmed=False, episode=0)
    schedule.capture(2, 104, jpeg(), goal)
    assert schedule.claim(now=104)["batch"] is None
    gated_capture(schedule, 3, 110, jpeg("white"), goal)
    batch = schedule.claim(now=111)["batch"]
    assert batch["trigger"] == "on_demand"
    artifact = json.loads((tmp_path / batch["frame_batch_ref"]).read_text())
    assert artifact["candidate_gate"]["detector"] == "RF-DETR"
    assert artifact["candidate_gate"]["condition"] == "person"


def test_brief_person_presence_captures_post_roll_after_the_person_leaves(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {"sampling": {"pre_roll_seconds": 2, "post_roll_seconds": 2}}, Benchmarks(tmp_path))
    schedule.capture(1, 100, jpeg(), {})
    schedule.person_sample(100, confirmed=True, episode=1)
    schedule.capture(2, 101, jpeg("white"), {})
    assert schedule.claim(now=101)["batch"] is None
    schedule.person_sample(101, confirmed=False, episode=1)
    schedule.capture(3, 102, jpeg("gray"), {})
    batch = schedule.claim(now=102)["batch"]
    artifact = json.loads((tmp_path / batch["frame_batch_ref"]).read_text())
    assert artifact["candidate_gate"]["confirmed"] is True
    assert artifact["selected_frames"][-1]["timestamp"] == 102
    complete_caption(tmp_path, batch["batch_id"], status="ok")
    schedule.capture(4, 120, jpeg(), {})
    assert schedule.claim(force=True, now=120)["batch"] is None


def test_person_gated_backlog_keeps_latest_window_and_never_overlaps_cosmos(tmp_path):
    metrics = Benchmarks(tmp_path)
    schedule = CaptionSchedule(tmp_path, "run", {"sampling": {"baseline_interval_seconds": 10}}, metrics)
    gated_capture(schedule, 1, 100, jpeg(), {})
    first = schedule.claim(invocation_id="one", now=101)["batch"]
    assert first["trigger"] == "person_gate"
    path = tmp_path / first["frame_batch_ref"]
    assert path.exists() and json.loads(path.read_text())["candidate_gate"]["detector"] == "RF-DETR"
    # Retried Core invocation gets its same artifact, never another model call.
    assert schedule.claim(invocation_id="one", now=102)["batch"] == first
    for revision, timestamp in enumerate((110, 120, 130), 2):
        gated_capture(schedule, revision, timestamp, jpeg("white"), {})
    assert schedule.claim(invocation_id="two", now=131)["batch"] is None
    assert schedule.snapshot()["pending_windows"] == 1
    assert schedule.snapshot()["skipped_windows"] == 2
    complete_caption(tmp_path, first["batch_id"], status="error")
    latest = schedule.claim(invocation_id="three", now=132)["batch"]
    batch = json.loads((tmp_path / latest["frame_batch_ref"]).read_text())
    assert batch["selected_frames"][-1]["timestamp"] == 130
    assert schedule.snapshot()["last_completion"]["status"] == "error"
    assert schedule.snapshot()["inflight"]["batch_id"] == latest["batch_id"]


def test_on_demand_goal_survives_slow_caption_and_baseline_replacement(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    goal = {"instruction": "A blocked corridor", "instruction_revision": 3, "last_command_id": "command-3"}
    assert schedule.claim(goal, force=True, invocation_id="command-3", now=100)["batch"] is None
    gated_capture(schedule, 1, 101, jpeg(), {})
    first = schedule.claim(invocation_id="first", now=102)["batch"]
    assert first["command_id"] == "command-3"
    schedule.claim(goal, force=True, invocation_id="command-new", now=103)
    gated_capture(schedule, 2, 130, jpeg("white"), {})
    complete_caption(tmp_path, first["batch_id"], status="ok")
    second = schedule.claim(invocation_id="second", now=131)["batch"]
    assert second["trigger"] == "on_demand" and second["instruction_revision"] == 3


def test_new_rule_replaces_pending_old_command_without_requesting_an_extra_caption(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    old = {"instruction": "A blocked corridor", "instruction_revision": 3, "last_command_id": "old"}
    new = {"instruction": "", "instruction_revision": 4, "last_command_id": "clear"}
    gated_capture(schedule, 1, 100, jpeg(), old)
    first = schedule.claim(old, invocation_id="first", now=101)["batch"]
    schedule.claim(old, force=True, invocation_id="old", now=102)
    assert schedule.claim(new, invocation_id="clear", now=103)["batch"] is None
    gated_capture(schedule, 2, 130, jpeg("white"), old)  # an already read old state cannot regress the pending rule
    complete_caption(tmp_path, first["batch_id"], status="ok")
    second = schedule.claim(invocation_id="second", now=131)["batch"]
    assert second["instruction_revision"] == 4 and second["instruction"] == ""
    assert second["command_id"] == "clear" and second["trigger"] == "person_gate"
    # An instruction cleared before any video arrives also supersedes the
    # durable startup request. It cannot return after a process restart.
    startup = CaptionSchedule(tmp_path / "startup", "run", {}, Benchmarks(tmp_path / "startup"))
    startup.claim(old, force=True, now=100)
    startup.claim(new, now=101)
    restarted = CaptionSchedule(tmp_path / "startup", "run", {}, Benchmarks(tmp_path / "startup"))
    gated_capture(restarted, 1, 102, jpeg(), new)
    assert restarted.claim(now=103)["batch"]["instruction_revision"] == 4


def test_caption_batch_uses_the_same_camera_override_as_person_events(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_SOURCE_CAMERA_ID", "approved-camera")
    schedule = CaptionSchedule(tmp_path, "run", {"video_source": {"camera_id": "saved-camera"}}, Benchmarks(tmp_path))
    gated_capture(schedule, 1, 100, jpeg(), {})
    batch = schedule.claim(now=101)["batch"]
    assert batch["camera_id"] == "approved-camera"


def test_lost_caption_completion_is_explicit_and_never_starts_overlapping_work(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    now = time.time()
    gated_capture(schedule, 1, now, jpeg(), {})
    first = schedule.claim(invocation_id="first", now=now - 400)["batch"]
    gated_capture(schedule, 2, now + 30, jpeg("white"), {})
    assert schedule.claim(invocation_id="second")["batch"] is None
    assert schedule.snapshot()["inflight_status"] == "stalled"
    restarted = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    assert restarted.snapshot()["inflight"]["batch_id"] == first["batch_id"]


@pytest.mark.parametrize("goal", ["A person is visible in the video.", "A visible person is not wearing a helmet."])
def test_person_gate_evidence_is_durable_and_never_publishes_a_notice(tmp_path, monkeypatch, goal):
    monkeypatch.setenv("VIDEO_SOURCE_CAMERA_ID", "approved-camera")
    root = tmp_path / "run-1"
    owner = PersonEvidence(root, "run-1", {"video_source": {"uri": "rtsp://private:password@camera/live"}}, Benchmarks(root))
    now = time.time()
    episode = {"episode": 1, "started_at": now - .2, "confirmed_at": now,
               "confidence": .9, "person_count": 1, "boxes": [PERSON]}
    owner.record(episode, jpeg(), {"instruction": goal}, "RF-DETR Small")
    evidence = json.loads(next((root / "person_events").glob("*.json")).read_text())
    assert evidence["purpose"] == "person_gate_only" and evidence["notify"] is False
    assert evidence["camera_id"] == "approved-camera"
    assert (root / evidence["frame_batch_ref"]).exists()
    assert not (root / "human.jsonl").exists()
    assert "password" not in (root / "events.jsonl").read_text()


def test_resident_person_gate_keeps_running_while_cosmos_is_inflight(tmp_path, monkeypatch):
    class Frames:
        revision = 0
        def latest_frame(self):
            self.revision += 1
            return self.revision, time.time(), jpeg()
    class Detector:
        variant, metadata, calls = "RF-DETR fixture", {}, 0
        def load(self):
            pass
        def detect(self, _jpeg):
            self.calls += 1
            return [PERSON]
    root = tmp_path / "run-1"
    detector = Detector()
    monitor = LiveMonitor(root, "run-1", {}, Frames(), lambda: pytest.fail("RF-DETR must not publish Chat"), detector=detector)
    gated_capture(monitor.caption_schedule, 1, time.time(), jpeg(), {})
    batch = monitor.caption_schedule.claim(invocation_id="slow-cosmos")["batch"]
    recorded = threading.Event()
    original = monitor.person_evidence.record
    def record(*args):
        original(*args)
        recorded.set()
    monkeypatch.setattr(monitor.person_evidence, "record", record)
    monitor.threads = [threading.Thread(target=monitor._person_loop), threading.Thread(target=monitor._caption_loop)]
    for thread in monitor.threads:
        thread.start()
    try:
        assert recorded.wait(3), "person inference waited for Cosmos completion"
        assert detector.calls >= 2
        assert monitor.caption_schedule.snapshot()["inflight"]["batch_id"] == batch["batch_id"]
        assert not (root / "human.jsonl").exists()
    finally:
        monitor.stop()
    assert all(not thread.is_alive() for thread in monitor.threads)


def test_failed_detector_cannot_open_cosmos_gate_or_claim_absence(tmp_path):
    class Detector:
        variant, metadata = "missing weights", {}
        def load(self):
            raise FileNotFoundError("RF-DETR checkpoint is missing; rebuild the CCTV worker image")
    monitor = LiveMonitor(tmp_path, "run", {}, SimpleNamespace(), lambda: None, detector=Detector())
    monitor._supervise("person", monitor._person_loop)
    assert monitor.status["person_detector"] == "failed"
    monitor.caption_schedule.capture(1, time.time(), jpeg(), {})
    assert monitor.caption_schedule.claim(force=True)["batch"] is None
    assert "checkpoint is missing" in (tmp_path / "events.jsonl").read_text()


def test_missing_or_corrupt_weights_fail_before_runtime_imports_or_downloads(tmp_path):
    detector = RFDETRPersonDetector(benchmarks=Benchmarks(tmp_path), root=tmp_path)
    with pytest.raises(FileNotFoundError, match="rebuild"):
        detector.load()
    assert detector.benchmarks.summary()["stages"][0]["errors"] == 1
    (tmp_path / "rf-detr-small.pth").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash"):
        verify_checkpoint("small", tmp_path)


def test_benchmarks_separate_versions_cold_start_errors_and_bound_retention(tmp_path):
    metrics = Benchmarks(tmp_path, {"benchmarks": {"max_samples": 100, "cohort": "fixture"}})
    for index in range(110):
        metrics.record("person.inference", index, variant="RF-DETR Small", metadata={"device": "test GPU", "token": "secret"})
    with pytest.raises(ValueError):
        with metrics.measure("memory.write", variant="MN memory"):
            raise ValueError("private content must not enter the benchmark")
    metrics.record("person.inference", 1000, variant="RF-DETR Medium", phase="cold")
    summary = metrics.summary()
    assert summary["retained_samples"] == 100
    assert "secret" not in json.dumps(summary) and "private content" not in json.dumps(summary)
    small = next(r for r in summary["stages"] if r["variant"] == "RF-DETR Small")
    assert small["ok"] == 98 and small["p95_ms"] >= small["p50_ms"]
    assert next(r for r in summary["stages"] if r["stage"] == "memory.write")["errors"] == 1
    assert next(r for r in summary["stages"] if r["phase"] == "cold")["ok"] == 1
    assert Benchmarks(tmp_path).summary()["max_samples"] == 100


def test_labeled_replay_measures_misses_false_events_and_confirmation_delay(tmp_path):
    (tmp_path / "frame.jpg").write_bytes(jpeg())
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps({"frames": [{"path": "frame.jpg", "timestamp": 1, "person_present": True}],
                                "person_events": [{"start": 1, "end": 2}]}))
    frames, events, fingerprint = load_dataset(path)
    assert len(frames) == 1 and len(fingerprint) == 64
    result = accuracy([True, True, False, False], [True, False, True, False], [1.2, 3], events)
    assert result["frame_presence"] == {"true_positive": 1, "false_positive": 1, "false_negative": 1,
        "true_negative": 1, "precision": .5, "recall": .5}
    assert result["person_events"]["false_events"] == 1
    assert result["person_events"]["p50_confirmation_delay_ms"] == 200
    path.write_text(json.dumps({"frames": [{"path": "../outside.jpg", "timestamp": 1, "person_present": True}]}))
    with pytest.raises(ValueError, match="relative"):
        load_dataset(path)


def test_explicit_no_event_labels_measure_false_alerts_separately_from_unlabeled_replay():
    negative = accuracy([True], [False], [1.2], [])
    assert negative["person_events"]["labeling_provided"] is True
    assert negative["person_events"]["false_events"] == 1
    unlabeled = accuracy([True], [False], [1.2], None)
    assert unlabeled["person_events"]["labeling_provided"] is False
    assert unlabeled["person_events"]["false_events"] is None


def test_comparison_excludes_warmup_preserves_accuracy_and_keeps_models_separate(tmp_path, monkeypatch):
    (tmp_path / "frame.jpg").write_bytes(jpeg())
    dataset = tmp_path / "labels.json"
    dataset.write_text(json.dumps({"frames": [
        {"path": "frame.jpg", "timestamp": 0, "person_present": False},
        {"path": "frame.jpg", "timestamp": .2, "person_present": True},
        {"path": "frame.jpg", "timestamp": .4, "person_present": True},
    ], "person_events": [{"start": .2, "end": .4}]}))
    calls = []
    class Detector:
        def __init__(self, settings, *, benchmarks):
            self.size = settings["model"]
            self.variant = "fixture " + self.size
            self.metadata = {}
            self.benchmarks = benchmarks
        def load(self):
            calls.append((self.size, "load"))
            self.benchmarks.record("person.model_load", 10, variant=self.variant, phase="cold", metadata=self.metadata)
        def detect(self, content):
            calls.append((self.size, "predict"))
            if self.benchmarks:
                self.benchmarks.record("person.inference", 1, variant=self.variant, metadata=self.metadata)
            return [PERSON] if self.size == "small" else []
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        empty_cache=lambda: calls.append(("gpu", "empty")), reset_peak_memory_stats=lambda: None)))
    output = tmp_path / "comparison"
    results = replay(dataset, output, ["small", "medium"], warmup=2, detector_factory=Detector)
    assert calls.index(("gpu", "empty")) < calls.index(("medium", "load"))
    assert results[0]["accuracy"]["frame_presence"]["false_positive"] == 1
    assert results[1]["accuracy"]["person_events"]["missed"] == 1
    for result in results:
        inference = next(row for row in result["timings"]["stages"] if row["stage"] == "person.inference")
        assert inference["ok"] == 3  # two warmup predictions were excluded
        assert inference["hardware_and_model"]["dataset_sha256"] == result["dataset_sha256"]
    assert (output / "comparison.json").exists()
    with pytest.raises(ValueError, match="empty output"):
        replay(dataset, output, ["small"], detector_factory=Detector)


def test_person_status_uses_fresh_detector_result_and_qualifies_recorded_playback():
    pipeline, warning = pipeline_status({"person_detector": "running", "last_person_frame_at": 100,
        "visible_people": 1, "source_profile": "bundled_demo", "captions": "running"}, {}, now=101)
    assert warning == ""
    summary = person_status_summary(pipeline)
    assert "1 person(s)" in summary and "Recorded demo playback" in summary
    stale, warning = pipeline_status(pipeline["person_events"], {}, now=110)
    assert stale["person_events"]["person_detector"] == "waiting_for_frames"
    assert person_status_summary(stale) == "" and "fresh video frames" in warning
    failed, warning = pipeline_status({"person_detector": "failed", "captions": "failed"}, {}, now=110)
    assert "Person detection stopped" in warning and "Caption sampling stopped" in warning
