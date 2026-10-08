"""Persist RF-DETR evidence before publishing a review notice through the SDK."""

import hashlib
import json
import time
import threading
import os
from datetime import datetime, timezone
from pathlib import Path

from mn_live_video_analysis_skill import write_frame_batch
from mn_sdk.blueprint_support import write_json
from mn_sdk.blueprint_support.observability import append_human_event
from mn_sdk.blueprint_support.step_execution import append_event

from .conversation_snapshot import event_snapshot
from .detection_policy import configured_alert_policy, configured_target_notice, evaluate_alert
from .person_events import person_goal, uses_person_events
from .alert_delivery import post_slack


class PersonNotices:
    def __init__(self, run_dir, run_id, config, benchmarks, publish_activity):
        self.root, self.run_id, self.config = Path(run_dir), run_id, config
        self.benchmarks, self.publish_activity = benchmarks, publish_activity
        try:
            self.state = json.loads((self.root / "person_notice_state.json").read_text())
        except FileNotFoundError:
            self.state = {}

    def publish(self, episode, jpeg, monitoring, variant):
        source = self.config.get("video_source") or {}
        camera_id = os.environ.get("VIDEO_SOURCE_CAMERA_ID") or source.get("camera_id", "cctv")
        identifier = hashlib.sha256(f"{self.run_id}:{episode['episode']}:{episode['confirmed_at']}".encode()).hexdigest()[:24]
        observed = datetime.fromtimestamp(episode["confirmed_at"], timezone.utc).isoformat().replace("+00:00", "Z")
        goal = person_goal(self.config, monitoring)
        detection = {"camera_id": camera_id, "source_profile": source.get("profile", "external"),
            "frame_seq": identifier, "confidence": episode["confidence"], "risk_level": "low",
            "detected_target": True, "detected_types": ["person"], "observed_at": observed,
            "summary": f"{episode['person_count']} person(s) visible in a sampled frame.",
            "monitoring_goal": goal, "detector": variant, "person_event": episode,
            "instruction_revision": int(monitoring.get("instruction_revision") or 0),
            "timestamp_basis": "worker_frame_availability"}
        decision = evaluate_alert(detection, configured_alert_policy(self.config), self.state,
                                  active_goal=goal, now=time.time())
        if not uses_person_events(goal):
            decision.update(notify=False, reason="complex_goal_uses_caption_reasoning")
        with self.benchmarks.measure("person.evidence", variant=variant):
            selected = [{"content": jpeg, "timestamp": episode["confirmed_at"], "score": episode["confidence"]}]
            path, _batch = write_frame_batch(self.root, batch_id=f"person-{identifier}", trigger="person_event",
                source={"name": camera_id}, instruction_revision=detection["instruction_revision"],
                instruction=goal, candidates=selected, selected=selected, schema="otterdesk.cctv_operator.frame_batch.v2")
            detection["frame_batch_ref"] = path.relative_to(self.root).as_posix()
            detection["goal_event"] = {"frame_path": f"frame_batches/person-{identifier}/frame-01.jpg",
                "observed_at": observed, "started_at": datetime.fromtimestamp(episode["started_at"], timezone.utc).isoformat(),
                "ended_at": observed, "timestamp_basis": "worker_frame_availability"}
            if decision["notify"]:
                detection["event_image"] = event_snapshot(self.root, detection["goal_event"],
                    run_id=self.run_id, camera_id=camera_id, frame_seq=identifier)
            write_json(self.root / "person_events" / f"{identifier}.json", {"schema": "otterdesk.cctv.person_event.v1", **detection, "alert_decision": decision})
        append_event(self.root, "cctv_operator_person_event", {key: value for key, value in detection.items() if key != "event_image"})
        if not decision["notify"]:
            return
        notice = configured_target_notice(detection, decision)
        notice["payload"].update(detector=variant, person_event=episode,
                                 timestamp_basis="worker_frame_availability")
        with self.benchmarks.measure("notice.publish", variant="SDK human notice + MCP activity"):
            append_human_event(self.run_id, "human_notice", notice["payload"], runs_root=self.root.parent,
                               blueprint_id="cctv_operator")
            self.publish_activity()
        self.benchmarks.record("person.capture_to_notice", max(0, (time.time() - episode["started_at"]) * 1000),
                               variant=variant, metadata={"timestamp_basis": "worker_frame_availability"})
        self.state["last_alert_wall_ts"] = decision["evaluated_at"]
        write_json(self.root / "person_notice_state.json", self.state)
        if decision["mode"] == "human_notice_and_slack" or os.environ.get("SLACK_ALERT_ENABLED", "false").lower() in {"1", "true", "yes", "on"}:
            # Destination latency cannot stop camera detection. No blueprint
            # retry/outbox: existing delivery adapter keeps its original contract.
            threading.Thread(target=self._slack, args=(notice["payload"]["message"], identifier), daemon=True).start()
        return notice

    def _slack(self, message, identifier):
        try:
            status, details = post_slack(message, enabled=True)
        except Exception:
            status, details = "error", {"reason": "slack_delivery_failed"}
        append_event(self.root, f"cctv_operator_slack_alert_{status}", {**details, "person_event_id": identifier})
