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
from cctv_operator.payloads.domain.person_events import PersonEpisodes, uses_person_events
from cctv_operator.payloads.domain.person_notices import PersonNotices
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


@pytest.mark.parametrize("goal,expected", [
    ("A person is visible in the video.", True), ("PERSON", True),
    ("A person is falling.", False), ("Two people stand together.", False),
    ("A person enters the restricted zone", False), ("No person is visible", False),
])
def test_only_simple_person_presence_goals_use_detector_alerts(goal, expected):
    assert uses_person_events(goal) is expected


def test_quiet_frames_caption_without_person_gate_and_backlog_keeps_latest_window(tmp_path):
    metrics = Benchmarks(tmp_path)
    schedule = CaptionSchedule(tmp_path, "run", {"sampling": {"baseline_interval_seconds": 10}}, metrics)
    schedule.capture(1, 100, jpeg(), {})
    first = schedule.claim(invocation_id="one", now=101)["batch"]
    assert first["trigger"] == "baseline"
    path = tmp_path / first["frame_batch_ref"]
    assert path.exists() and "candidate_gate" not in json.loads(path.read_text())
    # Retried Core invocation gets its same artifact, never another model call.
    assert schedule.claim(invocation_id="one", now=102)["batch"] == first
    for revision, timestamp in enumerate((110, 120, 130), 2):
        schedule.capture(revision, timestamp, jpeg("white"), {})
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
    schedule.capture(1, 101, jpeg(), {})
    first = schedule.claim(invocation_id="first", now=102)["batch"]
    assert first["command_id"] == "command-3"
    schedule.claim(goal, force=True, invocation_id="command-new", now=103)
    schedule.capture(2, 130, jpeg("white"), {})
    complete_caption(tmp_path, first["batch_id"], status="ok")
    second = schedule.claim(invocation_id="second", now=131)["batch"]
    assert second["trigger"] == "on_demand" and second["instruction_revision"] == 3


def test_new_rule_replaces_pending_old_command_without_requesting_an_extra_caption(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    old = {"instruction": "A blocked corridor", "instruction_revision": 3, "last_command_id": "old"}
    new = {"instruction": "", "instruction_revision": 4, "last_command_id": "clear"}
    schedule.capture(1, 100, jpeg(), old)
    first = schedule.claim(old, invocation_id="first", now=101)["batch"]
    schedule.claim(old, force=True, invocation_id="old", now=102)
    assert schedule.claim(new, invocation_id="clear", now=103)["batch"] is None
    schedule.capture(2, 130, jpeg("white"), old)  # an already read old state cannot regress the pending rule
    complete_caption(tmp_path, first["batch_id"], status="ok")
    second = schedule.claim(invocation_id="second", now=131)["batch"]
    assert second["instruction_revision"] == 4 and second["instruction"] == ""
    assert second["command_id"] == "clear" and second["trigger"] == "baseline"
    # An instruction cleared before any video arrives also supersedes the
    # durable startup request. It cannot return after a process restart.
    startup = CaptionSchedule(tmp_path / "startup", "run", {}, Benchmarks(tmp_path / "startup"))
    startup.claim(old, force=True, now=100)
    startup.claim(new, now=101)
    restarted = CaptionSchedule(tmp_path / "startup", "run", {}, Benchmarks(tmp_path / "startup"))
    restarted.capture(1, 102, jpeg(), new)
    assert restarted.claim(now=103)["batch"]["instruction_revision"] == 4


def test_caption_batch_uses_the_same_camera_override_as_person_events(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_SOURCE_CAMERA_ID", "approved-camera")
    schedule = CaptionSchedule(tmp_path, "run", {"video_source": {"camera_id": "saved-camera"}}, Benchmarks(tmp_path))
    schedule.capture(1, 100, jpeg(), {})
    batch = schedule.claim(now=101)["batch"]
    assert batch["camera_id"] == "approved-camera"


def test_lost_caption_completion_is_explicit_and_never_starts_overlapping_work(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    now = time.time()
    schedule.capture(1, now, jpeg(), {})
    first = schedule.claim(invocation_id="first", now=now - 400)["batch"]
    schedule.capture(2, now + 30, jpeg("white"), {})
    assert schedule.claim(invocation_id="second")["batch"] is None
    assert schedule.snapshot()["inflight_status"] == "stalled"
    restarted = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    assert restarted.snapshot()["inflight"]["batch_id"] == first["batch_id"]


def test_person_notice_has_durable_evidence_before_sdk_and_mcp_publication(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_SOURCE_CAMERA_ID", "approved-camera")
    root = tmp_path / "run-1"
    published = []
    def publish_activity():
        records = [json.loads(line) for line in (root / "human.jsonl").read_text().splitlines()]
        notice = records[-1]["payload"]
        assert (root / notice["frame_batch_ref"]).exists()
        assert list((root / "person_events").glob("*.json"))
        published.append(notice)
    owner = PersonNotices(root, "run-1", {"video_source": {"uri": "rtsp://private:password@camera/live"}},
                          Benchmarks(root), publish_activity)
    now = time.time()
    episode = {"episode": 1, "started_at": now - .2, "confirmed_at": now,
               "confidence": .9, "person_count": 1, "boxes": [PERSON]}
    owner.publish(episode, jpeg(), {}, "RF-DETR Small")
    assert len(published) == 1 and published[0]["requires_ack"] is True
    assert published[0]["detector"] == "RF-DETR Small"
    assert published[0]["camera_id"] == "approved-camera"
    assert "password" not in (root / "events.jsonl").read_text()
    # Distinct episodes are still subject to the operator's cooldown.
    owner.publish({**episode, "episode": 2, "confirmed_at": now + .1}, jpeg(), {}, "RF-DETR Small")
    assert len(published) == 1
    summary = owner.benchmarks.summary()
    assert {r["stage"] for r in summary["stages"]} >= {"notice.publish", "person.capture_to_notice"}


def test_resident_lanes_keep_person_notices_live_while_caption_batch_is_inflight(tmp_path):
    class Frames:
        revision = 0
        def ensure_started(self):
            pass
        def latest_frame(self):
            self.revision += 1
            return self.revision, time.time(), jpeg()
    class Detector:
        variant = "test detector"
        metadata = {}
        calls = 0
        def load(self):
            pass
        def detect(self, _jpeg):
            self.calls += 1
            return [PERSON]
    root = tmp_path / "run-1"
    delivered = threading.Event()
    detector = Detector()
    monitor = LiveMonitor(root, "run-1", {}, Frames(), delivered.set, detector=detector)
    # Hold the Cosmos lane indefinitely; detection has no dependency on it.
    monitor.caption_schedule.capture(1, time.time(), jpeg(), {})
    batch = monitor.caption_schedule.claim(invocation_id="slow-cosmos")["batch"]
    monitor.threads = [threading.Thread(target=monitor._person_loop), threading.Thread(target=monitor._caption_loop)]
    for thread in monitor.threads:
        thread.start()
    try:
        assert delivered.wait(3), "person event waited for caption completion"
        assert detector.calls >= 2
        assert monitor.caption_schedule.snapshot()["inflight"]["batch_id"] == batch["batch_id"]
        assert (root / "human.jsonl").exists()
        assert json.loads((root / "person_detector_state.json").read_text())["captions"] == "running"
    finally:
        monitor.stop()
    assert all(not thread.is_alive() for thread in monitor.threads)


def test_failed_detector_does_not_stop_independent_caption_lane(tmp_path):
    class Detector:
        variant, metadata = "missing weights", {}
        def load(self):
            raise FileNotFoundError("RF-DETR checkpoint is missing; rebuild the CCTV worker image")
    class Frames:
        def latest_frame(self):
            return 1, time.time(), jpeg()
    monitor = LiveMonitor(tmp_path, "run", {}, Frames(), lambda: None, detector=Detector())
    monitor._supervise("person", monitor._person_loop)
    assert monitor.status["person_detector"] == "failed"
    monitor.caption_schedule.capture(1, time.time(), jpeg(), {})
    assert monitor.caption_schedule.claim()["batch"] is not None
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
