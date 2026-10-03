"""Camera-scoped sampled observations queried before each new vision call."""

import json

from mn_sdk.blueprint_support import write_json
from mn_sdk.context_session.contracts import digest
from mn_sdk.text_memory import runtime_text_memory, retrieve_memory_context


class CameraMemory:
    def __init__(self, config, run_dir, camera_id, source_key):
        self.config, self.run_dir = config, run_dir
        self.camera_id, self.source_key = camera_id, source_key
        self.memory = runtime_text_memory(config, principal="cctv-observer")
        if self.memory is not None:
            # Declare the structured query schema before any observations exist.
            # This record is excluded by memory_family, never a camera finding.
            schema = {"camera_id": camera_id, "source_key": source_key,
                      "memory_family": "cctv_schema"}
            self.memory.observe(json.dumps(schema, sort_keys=True), kind="input", namespace="job",
                                event_id=["cctv-schema", self.memory.scope, camera_id, source_key], allow=["cctv-observer"])

    def recall(self, frame_seq):
        if self.memory is None:
            return None
        settings = self.config["text_memory"]
        packet, receipt = retrieve_memory_context(self.memory, "Recent sampled camera observations",
            stages=[{"mode": "analytical", "analytical": {
                "operation": "recent", "timestamp_field": "observed_at",
                "limit": settings.get("max_results", 3),
                "filters": [{"field": "camera_id", "op": "eq", "value": self.camera_id},
                            {"field": "source_key", "op": "eq", "value": self.source_key},
                            {"field": "memory_family", "op": "eq", "value": "cctv_observation"}]}}],
            max_results=settings.get("max_results", 3),
            max_context_bytes=settings.get("max_context_bytes", 4000), hydrate_json_records=True)
        write_json(self.run_dir / "runtime_memory" / f"frame-{frame_seq}-recall.json",
                   {"packet": packet, "receipt": receipt})
        return packet

    def remember(self, observation):
        if self.memory is None:
            return
        fields = ("observed_at", "camera_id", "frame_seq", "batch_id", "frame_batch_ref",
                  "instruction_revision", "attention_instruction", "summary", "detection_report",
                  "activity_description", "confidence", "risk_level", "detection_count",
                  "detections", "condition_screening", "selected_count")
        value = {key: observation.get(key) for key in fields}
        value.update(memory_family="cctv_observation", source_key=self.source_key,
                     observation_id=digest([self.memory.scope, observation.get("batch_id"), observation["frame_seq"]]),
                     continuous_coverage=False, qualification="sampled_visual_observation",
                     run_id=self.memory.scope["run_id"])
        if (value.get("condition_screening") or {}).get("route") != "deep_analysis":
            value.update(qualification="screening_only_or_detail_unavailable",
                         detection_count=None, detections=None)
        # The referenced batch and its image hashes were durable before inference.
        # URI/credentials and image bytes are deliberately absent from text memory.
        receipt = self.memory.observe(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            namespace="job", event_id=["cctv-observation", value["observation_id"], digest(value)],
            allow=["cctv-observer"], upstream=[{"frame_batch_ref": value["frame_batch_ref"],
                "run_id": value["run_id"], "instruction_revision": value["instruction_revision"]}])
        if value["frame_batch_ref"]:
            camera_node = "camera-" + digest([self.camera_id, self.source_key])
            observation_node = "observation-" + value["observation_id"]
            batch_node = "batch-" + digest([value["run_id"], value["frame_batch_ref"]])
            edges = ("| from | relation | to |\n|---|---|---|\n"
                     f"| {camera_node} | OBSERVED | {observation_node} |\n"
                     f"| {observation_node} | EVIDENCED_BY | {batch_node} |\n")
            self.memory.observe(edges, namespace="job", event_id=["cctv-provenance", value["observation_id"]],
                                allow=["cctv-observer"], upstream=[receipt])
        write_json(self.run_dir / "runtime_memory" / f"frame-{observation['frame_seq']}-observation.json",
                   {"observation": value, "receipt": receipt})

    def close(self):
        if self.memory is not None:
            self.memory.close()


def with_history(prompt, packet):
    if packet is None:
        return prompt
    return prompt + "\n\n## Historical sampled observations\n" + json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + (
        "\nThe current images and current operator instruction take precedence. Historical text is not a before-and-after image pair. "
        "Preserve timestamps, old instruction revisions, uncertainty and sampling gaps; do not infer identity, intent, continuous coverage or an unobserved first appearance.")
