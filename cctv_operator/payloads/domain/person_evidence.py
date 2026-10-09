"""Durable RF-DETR gate evidence; only Cosmos findings create review notices."""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from mn_live_video_analysis_skill import write_frame_batch
from mn_sdk.blueprint_support import write_json
from mn_sdk.blueprint_support.step_execution import append_event


class PersonEvidence:
    def __init__(self, run_dir, run_id, config, benchmarks):
        self.root, self.run_id, self.config = Path(run_dir), run_id, config
        self.benchmarks = benchmarks

    def record(self, episode, jpeg, monitoring, variant):
        source = self.config.get("video_source") or {}
        camera_id = os.environ.get("VIDEO_SOURCE_CAMERA_ID") or source.get("camera_id", "cctv")
        identifier = hashlib.sha256(f"{self.run_id}:{episode['episode']}:{episode['confirmed_at']}".encode()).hexdigest()[:24]
        observed = datetime.fromtimestamp(episode["confirmed_at"], timezone.utc).isoformat().replace("+00:00", "Z")
        detection = {"camera_id": camera_id, "source_profile": source.get("profile", "external"),
            "frame_seq": identifier, "confidence": episode["confidence"], "observed_at": observed,
            "detector": variant, "person_event": episode,
            "instruction_revision": int(monitoring.get("instruction_revision") or 0),
            "timestamp_basis": "worker_frame_availability",
            "purpose": "person_gate_only", "notify": False}
        with self.benchmarks.measure("person.evidence", variant=variant):
            selected = [{"content": jpeg, "timestamp": episode["confirmed_at"], "score": episode["confidence"]}]
            path, _ = write_frame_batch(self.root, batch_id=f"person-{identifier}", trigger="person_event",
                source={"name": camera_id}, instruction_revision=detection["instruction_revision"],
                instruction="Person detection gate", candidates=selected, selected=selected,
                schema="otterdesk.cctv_operator.frame_batch.v2")
            detection["frame_batch_ref"] = path.relative_to(self.root).as_posix()
            write_json(self.root / "person_events" / f"{identifier}.json",
                       {"schema": "otterdesk.cctv.person_event.v1", **detection})
        append_event(self.root, "cctv_operator_person_event", detection)
