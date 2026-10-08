"""Resident person detection and independent caption sampling for one camera."""

import json
import math
import threading
import time
from pathlib import Path

from mn_sdk.blueprint_support import write_json
from mn_sdk.blueprint_support.step_execution import append_event
from mn_sdk_models.local_service import LocalModelService
from mn_live_video_analysis_skill import redact_source_urls

from .benchmarks import Benchmarks
from .caption_schedule import BINDING_FILE, CaptionSchedule
from .monitoring import load_monitoring_state
from .person_detector import RFDETRPersonDetector
from .person_events import PersonEpisodes
from .person_notices import PersonNotices
from .detection_policy import configured_alert_policy


class LiveMonitor:
    def __init__(self, run_dir, run_id, config, frame_source, publish_activity, *, detector=None):
        self.root, self.run_id, self.config = Path(run_dir), run_id, config
        self.frame_source = frame_source
        self.benchmarks = Benchmarks(run_dir, config)
        settings = config.get("person_detector") or {}
        self.fps = float(settings.get("fps", 5))
        if not math.isfinite(self.fps) or not .5 <= self.fps <= 15:
            raise ValueError("person_detector.fps must be between .5 and 15")
        self.detector = detector or RFDETRPersonDetector(settings, benchmarks=self.benchmarks)
        try:
            prior = json.loads((self.root / "person_detector_state.json").read_text())
        except FileNotFoundError:
            prior = {}
        self.episodes = PersonEpisodes(settings, prior.get("episodes"))
        self.status = {"person_detector": "starting", "captions": "starting"}
        self.persist_lock = threading.Lock()
        self.caption_schedule = CaptionSchedule(run_dir, run_id, config, self.benchmarks)
        self.notices = PersonNotices(run_dir, run_id, config, self.benchmarks, publish_activity)
        self.stop_event = threading.Event()
        self.threads = []
        self.service = None

    def start(self):
        self.service = LocalModelService(self.request, binding_path=self.root / BINDING_FILE, scope=self.run_id).start()
        self.frame_source.ensure_started()
        for name, target in (("person", self._person_loop), ("caption-sampling", self._caption_loop)):
            thread = threading.Thread(target=self._supervise, args=(name, target), name=f"cctv-{name}", daemon=True)
            self.threads.append(thread)
            thread.start()
        return self

    def _supervise(self, stage, target):
        try:
            target()
        except Exception as exc:
            # The two lanes have explicit independent health. A failed detector
            # never closes the caption path or makes an absence observation.
            self.status["person_detector" if stage == "person" else "captions"] = "failed"
            append_event(self.root, "cctv_operator_frame_analysis_failed", {"stage": stage,
                "error": redact_source_urls(f"{type(exc).__name__}: {exc}")[:800],
                "summary": f"{stage} stopped. Review worker logs and rebuild or restart."})
            self._persist()

    def _person_loop(self):
        self.detector.load()
        self.status["person_detector"] = "ready"
        last_revision = 0
        while not self.stop_event.is_set():
            started = time.monotonic()
            revision, timestamp, jpeg = self.frame_source.latest_frame()
            if jpeg and revision != last_revision:
                skipped = max(0, revision - last_revision - 1) if last_revision else 0
                last_revision = revision
                metadata = {**self.detector.metadata, "fps": self.fps, "timestamp_basis": "worker_frame_availability"}
                self.benchmarks.record("stream.frame_age", max(0, (time.time() - timestamp) * 1000),
                                       variant=self.detector.variant, metadata=metadata)
                if skipped:
                    self.benchmarks.record("person.coverage", 0, variant=self.detector.variant, status="skipped",
                                           metadata={**metadata, "skipped_frames": skipped})
                people = [person for person in self.detector.detect(jpeg)
                          if person["confidence"] >= configured_alert_policy(self.config)["min_confidence"]]
                monitoring = load_monitoring_state(self.root)
                with self.benchmarks.measure("person.policy", variant=self.detector.variant):
                    episode = self.episodes.update(people, timestamp,
                        revision=int(monitoring.get("instruction_revision") or 0))
                self.status.update(person_detector="running", last_person_frame_at=timestamp, visible_people=len(people))
                self._persist()
                if episode:
                    self.notices.publish(episode, jpeg, monitoring, self.detector.variant)
            self.stop_event.wait(max(.01, 1 / self.fps - (time.monotonic() - started)))

    def _caption_loop(self):
        self.status["captions"] = "running"
        self._persist()
        while not self.stop_event.is_set():
            revision, timestamp, jpeg = self.frame_source.latest_frame()
            if jpeg:
                self.caption_schedule.capture(revision, timestamp, jpeg, load_monitoring_state(self.root))
            self.stop_event.wait(1 / self.caption_schedule.policy.burst_candidate_fps)

    def _persist(self):
        with self.persist_lock:
            write_json(self.root / "person_detector_state.json", {**self.status, "model": self.detector.variant,
                "episodes": dict(self.episodes.state), "configured_fps": self.fps,
                "source_profile": (self.config.get("video_source") or {}).get("profile", "external"),
                "timestamp_basis": "worker_frame_availability"})

    def request(self, payload):
        if payload.get("operation") == "claim_caption":
            monitoring = payload.get("monitoring") or {}
            if not isinstance(monitoring, dict) or len(str(monitoring.get("instruction") or "")) > 500:
                raise ValueError("invalid caption monitoring state")
            invocation = payload.get("invocation_id") or ""
            if not isinstance(invocation, str) or len(invocation) > 500:
                raise ValueError("invalid caption invocation identity")
            return self.caption_schedule.claim(monitoring, force=payload.get("force") is True, invocation_id=invocation)
        if payload.get("operation") == "status":
            return {**self.status, "caption_schedule": self.caption_schedule.snapshot()}
        raise ValueError("unsupported resident monitor operation")

    def stop(self):
        self.stop_event.set()
        if self.service:
            self.service.stop()
        for thread in self.threads:
            thread.join(timeout=3)
