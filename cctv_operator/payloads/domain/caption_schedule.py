"""Fixed RF-DETR person gate and bounded Cosmos admission before Core delivery."""

import hashlib
import io
import json
import os
import threading
import time
from collections import deque
from pathlib import Path

from mn_live_video_analysis_skill import SamplingPolicy, redact_source_uri, select_diverse_frames, write_frame_batch
from mn_sdk.blueprint_support import write_json
from mn_sdk_models.local_service import local_model_request

from .monitoring import initial_monitoring_state

BINDING_FILE = "resident_monitor_binding.json"


def complete_caption(run_dir, batch_id, *, status):
    if batch_id:
        write_json(Path(run_dir) / "caption_completion.json", {"batch_id": batch_id, "status": status, "at": time.time()})


def claim_caption(run_dir, run_id, *, monitoring, force=False, invocation_id=""):
    return local_model_request(Path(run_dir) / BINDING_FILE, run_id,
        {"operation": "claim_caption", "monitoring": monitoring, "force": bool(force), "invocation_id": invocation_id}, timeout=20)


class CaptionSchedule:
    def __init__(self, run_dir, run_id, config, benchmarks):
        self.root, self.run_id, self.config, self.benchmarks = Path(run_dir), run_id, config, benchmarks
        self.policy = SamplingPolicy.from_mapping(config.get("sampling"))
        self.window = self.policy.pre_roll_seconds + self.policy.post_roll_seconds
        if not .5 <= self.window <= 30:
            raise ValueError("caption sequence window must be between .5 and 30 seconds")
        self.frames = deque(maxlen=max(2, int(self.window * self.policy.burst_candidate_fps) + 2))
        self.lock = threading.Lock()
        self.pending = None
        self.last_revision = None
        self.last_capture_at = None
        self.person_gate = None
        self.gate_window = None
        self.gate_max_age = float((config.get("person_detector") or {}).get("max_gap_seconds", 2))
        try:
            self.state = json.loads((self.root / "caption_schedule.json").read_text())
        except FileNotFoundError:
            self.state = {"sequence": 0, "inflight": None, "skipped_windows": 0, "last_offered_at": None, "call_times": []}
        self.pending_requested_command = self.state.get("pending_requested_command")

    def person_sample(self, timestamp, *, confirmed, episode):
        # RF-DETR owns this signal. Monitoring goals cannot replace the gate.
        # No image work, model call or durable write blocks person inference.
        with self.lock:
            prior = self.person_gate or {}
            if timestamp <= prior.get("at", float("-inf")):
                return
            started = prior.get("started_at", timestamp)
            if not confirmed or not prior.get("confirmed") or prior.get("episode") != episode:
                started = timestamp
            self.person_gate = {"at": timestamp, "confirmed": bool(confirmed),
                                "started_at": started, "episode": episode}
            last = self.state.get("last_offered_at")
            if confirmed and self.gate_window is None and (
                    last is None or timestamp - last >= max(0,
                        self.policy.baseline_interval_seconds - self.policy.post_roll_seconds)):
                # Preserve a brief confirmed appearance until its post-roll is
                # captured, even if the person leaves before the window ends.
                self.gate_window = dict(self.person_gate)

    def _gate_open(self, timestamp):
        gate = self.person_gate
        return bool(gate and gate["confirmed"] and
                    0 <= timestamp - gate["at"] <= self.gate_max_age and
                    timestamp - gate["started_at"] >= self.policy.post_roll_seconds)

    def capture(self, revision, timestamp, jpeg, monitoring):
        with self.lock:
            self._refresh_monitoring(monitoring)
            if revision == self.last_revision or (self.last_capture_at is not None and
                    timestamp - self.last_capture_at < 1 / self.policy.burst_candidate_fps):
                return
            self.last_revision, self.last_capture_at = revision, timestamp
            from PIL import Image
            image = Image.open(io.BytesIO(jpeg)).convert("RGB")
            image.thumbnail((self.policy.frame_jpeg_max_width, self.policy.frame_jpeg_max_width))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=85)
            self.frames.append({"content": buffer.getvalue(), "timestamp": timestamp, "score": 0})
            while self.frames and timestamp - self.frames[0]["timestamp"] > self.window:
                self.frames.popleft()
            requested = self.pending_requested_command
            gate = self.gate_window
            if gate is None or timestamp - gate["at"] < self.policy.post_roll_seconds:
                return
            self.gate_window = None
            if timestamp - gate["at"] > self.window:
                # The rolling images no longer contain the confirmed sample.
                self.state["skipped_windows"] += 1
                self._persist()
                return
            if requested is not None:
                self.pending_requested_command = None
                self._offer(requested, timestamp, "on_demand", gate=gate)
            else:
                self._offer(monitoring, timestamp, "person_gate", gate=gate)

    def _offer(self, monitoring, now, trigger, *, gate=None):
        if not self.frames:
            return
        if self.pending is not None:
            if (int(self.pending["monitoring"].get("instruction_revision") or 0) >
                    int(monitoring.get("instruction_revision") or 0)):
                monitoring = self.pending["monitoring"]
            if (self.pending["trigger"] == "on_demand" and trigger == "person_gate" and
                    int(self.pending["monitoring"].get("instruction_revision") or 0) >=
                    int(monitoring.get("instruction_revision") or 0)):
                # Keep the requested revision, but refresh its images while a
                # previous caption runs. A person window cannot discard the command.
                monitoring = self.pending["monitoring"]
                trigger = "on_demand"
            self.state["skipped_windows"] += 1
            self.benchmarks.record("caption.coverage", 0, variant="person-gated cadence", status="skipped",
                                   metadata={"skipped_windows": 1})
        self.pending = {"frames": list(self.frames), "monitoring": dict(monitoring), "offered_at": now,
                        "trigger": trigger, "gate": dict(gate or self.person_gate)}
        self.state["last_offered_at"] = now
        self._persist()

    def _refresh_monitoring(self, monitoring):
        revision = int(monitoring.get("instruction_revision") or 0)
        if self.pending is not None and revision > int(self.pending["monitoring"].get("instruction_revision") or 0):
            # An already scheduled window follows the latest rule. A superseded
            # on-demand command cannot hold its old rule ahead of a newer one.
            self.pending.update(monitoring=dict(monitoring), trigger="person_gate")
        requested = self.pending_requested_command
        if requested is not None and revision > int(requested.get("instruction_revision") or 0):
            self.pending_requested_command = None

    def _persist(self):
        write_json(self.root / "caption_schedule.json", self.snapshot())

    def snapshot(self):
        inflight = self.state.get("inflight")
        return {"schema": "otterdesk.cctv.caption_schedule.v1", **self.state, "pending_requested_command": self.pending_requested_command,
                "gate": {"detector": "RF-DETR", "condition": "person", **(self.person_gate or {})},
                "pending_windows": int(self.pending is not None),
                "inflight_status": ("stalled" if inflight and time.time() - inflight["claimed_at"] > 300
                                    else "processing" if inflight else "idle"),
                "coverage": "sampled windows; overwritten pending windows are counted"}

    def claim(self, monitoring=None, *, force=False, invocation_id="", now=None):
        now = time.time() if now is None else now
        with self.lock:
            if monitoring is not None:
                self._refresh_monitoring(monitoring)
            inflight = self.state.get("inflight")
            if inflight:
                try:
                    completion = json.loads((self.root / "caption_completion.json").read_text())
                except FileNotFoundError:
                    completion = {}
                if completion.get("batch_id") == inflight["batch_id"]:
                    self.state["inflight"] = None
                    self.state["last_completion"] = completion
                elif invocation_id and inflight.get("invocation_id") == invocation_id:
                    return {"batch": inflight["message"], "state": self.snapshot()}
            if force:
                if self.frames and self._gate_open(now):
                    self._offer(monitoring or initial_monitoring_state(), now, "on_demand")
                else:
                    self.pending_requested_command = monitoring or initial_monitoring_state()
            if self.state.get("inflight") or not self.pending:
                self._persist()
                return {"batch": None, "state": self.snapshot()}
            self.state["call_times"] = [at for at in self.state["call_times"] if now - at < 60]
            if len(self.state["call_times"]) >= self.policy.max_calls_per_minute:
                return {"batch": None, "state": self.snapshot()}
            pending = self.pending
            selected = select_diverse_frames(pending["frames"], limit=self.policy.max_model_frames)
            instruction = pending["monitoring"]
            self.state["sequence"] += 1
            batch_id = "caption-" + hashlib.sha256(
                f"{self.run_id}:{self.state['sequence']}:{pending['offered_at']}".encode()).hexdigest()[:24]
            source = self.config.get("video_source") or {}
            camera_id = os.environ.get("VIDEO_SOURCE_CAMERA_ID") or source.get("camera_id", "cctv")
            path, batch = write_frame_batch(self.root, batch_id=batch_id, trigger=pending["trigger"],
                source={"mode": "stream", "uri": redact_source_uri(os.environ.get("VIDEO_SOURCE_URI") or source.get("uri", "")),
                        "name": camera_id},
                instruction=str(instruction.get("instruction") or ""),
                instruction_revision=int(instruction.get("instruction_revision") or 0),
                candidates=pending["frames"], selected=selected, schema="otterdesk.cctv_operator.frame_batch.v2",
                metadata={"camera_id": camera_id, "command_id": instruction.get("last_command_id"),
                          "candidate_gate": {"detector": "RF-DETR", "condition": "person", **pending["gate"]},
                          "caption_offered_at": pending["offered_at"], "caption_claimed_at": now,
                          "timestamp_basis": "worker_frame_availability", "skipped_caption_windows": self.state["skipped_windows"]})
            message = {key: batch[key] for key in ("batch_id", "trigger", "instruction", "instruction_revision",
                       "camera_id", "command_id", "candidate_count", "selected_count")}
            message.update(frame_batch_ref=path.relative_to(self.root).as_posix(), tick_seq=self.state["sequence"])
            self.state["inflight"] = {"batch_id": batch_id, "claimed_at": now, "invocation_id": invocation_id, "message": message}
            self.state["call_times"].append(now)
            self.pending = None
            self.benchmarks.record("caption.queue_wait", max(0, (now - pending["offered_at"]) * 1000),
                                   variant="one in flight / one latest pending", metadata={"frames": len(selected)})
            self._persist()
            return {"batch": message, "state": self.snapshot()}
