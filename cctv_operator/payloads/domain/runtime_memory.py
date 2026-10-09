"""Camera-scoped sampled observations queried before each new vision call."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mn_sdk.blueprint_support import write_json
from mn_sdk.context_session.contracts import digest
from mn_sdk.text_memory import runtime_text_memory, retrieve_memory_context
from mn_live_video_analysis_skill import redact_source_uri
from .camera_knowledge import observation_record

CAMERA_MARKDOWN_MAX_BYTES = 4 * 1024 * 1024


class CameraMemory:
    def __init__(self, config, run_dir, camera_id, source_key):
        self.config, self.run_dir = config, run_dir
        self.camera_id, self.source_key = camera_id, source_key
        self.last_recall_receipt = {}
        self.memory = runtime_text_memory(config, principal="cctv-observer")
        if self.memory is not None:
            from mn_context_engine_sdk.intelligent_system import RuntimeRecord
            # Declare the structured query schema before any observations exist.
            # This record is excluded by memory_family, never a camera finding.
            schema_id = "camera-schema-v2-" + digest([self.memory.scope, camera_id, source_key])
            clock = self.memory.restore_checkpoint(schema_id)
            if clock is None:
                clock = {"declared_at": datetime.now(timezone.utc).isoformat()}
                self.memory.checkpoint(schema_id, clock)
            self.memory.record(RuntimeRecord(schema_id, "Camera history schema",
                clock["declared_at"], "schema_declaration_not_camera_observation",
                {"camera_id": camera_id, "source_key": source_key, "run_id": self.memory.scope["run_id"],
                 "memory_family": "cctv_schema"}, kind="constraint"),
                namespace="job", event_id=schema_id, allow=["cctv-observer"])

    def recall(self, frame_seq, *, after="", before="", limit=None,
               query="Recent sampled camera observations", run_id=None):
        if self.memory is None:
            return None
        settings = self.config["text_memory"]
        filters = [{"field": "camera_id", "op": "eq", "value": self.camera_id},
                   {"field": "source_key", "op": "eq", "value": self.source_key},
                   {"field": "memory_family", "op": "eq", "value": "cctv_observation"}]
        if run_id:
            filters.append({"field": "run_id", "op": "eq", "value": run_id})
        for value, operation in ((after, "gte"), (before, "lte")):
            if value:
                if len(value) > 64:
                    raise ValueError("history bound is too long")
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("history bounds require a timezone")
                canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                filters.append({"field": "timestamp", "op": operation, "value": canonical})
        count = limit or settings.get("max_results", 3)
        packet, receipt = retrieve_memory_context(self.memory, query,
            stages=[{"mode": "analytical", "analytical": {
                "operation": "recent", "timestamp_field": "timestamp",
                "limit": count, "filters": filters}}],
            max_results=count,
            max_context_bytes=settings.get("max_context_bytes", 4000), hydrate_runtime_records=True)
        write_json(self.run_dir / "runtime_memory" / f"frame-{frame_seq}-recall.json",
                   {"packet": packet, "receipt": receipt})
        self.last_recall_receipt = receipt
        return packet

    def remember(self, observation):
        if self.memory is None:
            return
        fields = ("observed_at", "camera_id", "frame_seq", "batch_id", "frame_batch_ref",
                  "instruction_revision", "attention_instruction", "summary", "detection_report",
                  "activity_description", "confidence", "risk_level", "detection_count",
                  "detections", "condition_screening", "selected_count",
                  "scene_understanding", "risk_predictions", "uncertainties",
                  "capture_started_at", "capture_ended_at", "frame_timestamps",
                  "timestamp_basis", "source_profile", "analyzed_at")
        fields += ("goal_event", "monitoring_goal", "detected_target", "helmet_observations", "goal_validation")
        value = {key: observation.get(key) for key in fields}
        value.update(memory_family="cctv_observation", source_key=self.source_key,
                     observation_id=digest([self.memory.scope, observation.get("batch_id"), observation["frame_seq"]]),
                     continuous_coverage=False, qualification="sampled_visual_observation",
                     run_id=self.memory.scope["run_id"])
        if value["camera_id"] != self.camera_id:
            raise ValueError("camera observation does not match its memory scope")
        if not isinstance(value["observed_at"], str) or not value["observed_at"]:
            raise ValueError("camera observations require their actual timestamp")
        value["camera_node_id"] = digest([self.camera_id, self.source_key])
        value["batch_node_id"] = digest([value["run_id"], value["frame_batch_ref"]])
        if (value.get("condition_screening") or {}).get("route") != "deep_analysis":
            value.update(qualification="screening_only_or_detail_unavailable",
                         detection_count=None, detections=None)
        # The referenced batch and its image hashes were durable before inference.
        # URI/credentials and image bytes are deliberately absent from text memory.
        record = observation_record(value)
        receipt = self.memory.record(record,
            namespace="job", event_id=["cctv-observation", value["observation_id"], digest(value)],
            allow=["cctv-observer"], upstream=[{"frame_batch_ref": value["frame_batch_ref"],
                "run_id": value["run_id"], "instruction_revision": value["instruction_revision"]}])
        write_json(self.run_dir / "runtime_memory" / f"frame-{observation['frame_seq']}-observation.json",
                   {"observation": value, "markdown": record.markdown(), "receipt": receipt})
        publish_camera_markdown(self.config, self.run_dir, value, record.markdown())

    def close(self):
        if self.memory is not None:
            self.memory.close()


def read_video_history(config, run_dir, *, query="Recent sampled camera observations",
                       after="", before="", current_run=False, request_id="chat-history"):
    """Read complete authored Markdown accounts, never images or report projections."""
    bounds = []
    for value in (after, before):
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError("history time bounds exceed limits")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
        if parsed is not None and parsed.tzinfo is None:
            raise ValueError("history bounds require a timezone")
        bounds.append(parsed)
    if all(bounds) and bounds[0] > bounds[1]:
        raise ValueError("history after must precede before")
    source = config.get("video_source") or {}
    uri = os.environ.get("VIDEO_SOURCE_URI") or source.get("uri", "")
    source_key = hashlib.sha256(redact_source_uri(uri).encode()).hexdigest()
    camera_id = os.environ.get("VIDEO_SOURCE_CAMERA_ID") or source.get("camera_id") or "cctv"
    memory = CameraMemory(config, run_dir, camera_id, source_key)
    try:
        packet = memory.recall(request_id, query=query, after=after, before=before,
                               limit=12, run_id=memory.memory.scope["run_id"]
                               if current_run and memory.memory is not None else None)
        aliases = {row["citation"] for row in (packet or {}).get("evidence", [])}
        citations = {alias: handles for alias, handles in memory.last_recall_receipt.get("citations", {}).items()
                     if alias in aliases}
        return {"schema_version": "mn.cctv.video_history.v1", "history": packet,
                "citations": citations, "continuous_coverage": False,
                "qualification": "Sampled observations; forecasts are predictions, not observed events. "
                    "Up to twelve most recent matching Markdown accounts; not exhaustive. "
                    "Skipped caption windows do not prove absence. Capture times describe playback for recorded demo footage. "
                    "Repeated observations do not establish unique people or a total number of appearances."}
    finally:
        memory.close()


def with_history(prompt, packet):
    if packet is None:
        return prompt
    return prompt + "\n\n## Historical sampled observations\n" + json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + (
        "\nThe current images and current operator instruction take precedence. Historical text is not a before-and-after image pair. "
        "Preserve timestamps, old instruction revisions, uncertainty and sampling gaps; do not infer identity, intent, continuous coverage or an unobserved first appearance.")


def publish_camera_markdown(config, run_dir, observation, markdown):
    """Bounded hourly sources let the Job answer after the video service stops."""
    output = (config.get("outputs") or {}).get("output_folder")
    root = Path(output) if output else run_dir
    directory = root / "context_sources" / "outputs"
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00"))
    stem = f"camera-{observation['camera_node_id']}-{timestamp:%Y%m%dT%H}"
    marker = f"<!-- observation:{observation['observation_id']} -->"
    header = "# Sampled video history\n\nPredictions are hypotheses, not observed events. Demo playback is recorded footage.\n"
    entry = "\n" + marker + "\n" + markdown + "\n"
    if len((header + entry).encode("utf-8")) > CAMERA_MARKDOWN_MAX_BYTES:
        raise ValueError("camera observation exceeds the conversation source limit")
    part = 1
    while True:
        suffix = "" if part == 1 else f"-{part:04d}"
        path = directory / f"{stem}{suffix}.md"
        prior = path.read_text(encoding="utf-8") if path.exists() else header
        if marker in prior:
            return
        body = prior + entry
        if len(body.encode("utf-8")) <= CAMERA_MARKDOWN_MAX_BYTES:
            break
        part += 1
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(path)
