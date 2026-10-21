"""Immutable admitted camera windows, including every selected frame's identity."""

import json
import math
import re

from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.integrations.block_files import capture_file, materialize_file
from mn_sdk_common.publication import ArtifactWrite

SCHEMA = "otterdesk.cctv.frame_evidence.v1"
MAX_BYTES = 32 * 1024 * 1024
CLAIM_FIELDS = {"batch_id", "frame_batch_ref", "trigger", "instruction", "instruction_revision",
                "camera_id", "command_id", "candidate_count", "selected_count", "tick_seq"}


def _scope(block):
    return {"job_id": block.job_id, "run_id": block.run_id,
            "source_sampling": fingerprint({key: block.original_config.get(key)
                for key in ("video_source", "sampling")})}


def capture_batch(block, message, *, max_frames):
    if not isinstance(message, dict) or set(message) != CLAIM_FIELDS:
        raise ValueError("Caption claim has an invalid evidence declaration")
    batch_id = message["batch_id"]
    if not isinstance(batch_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", batch_id):
        raise ValueError("Caption batch identity is invalid")
    prefix = f"frame_batches/{batch_id}/"
    if message["frame_batch_ref"] != prefix + "batch.json":
        raise ValueError("Caption batch path differs from its identity")

    def capture(path, limit):
        source = block.store.path(path)
        if not 0 < source.stat().st_size <= limit:
            raise ValueError("Caption evidence exceeds its byte bound")
        ref = capture_file(block, source, key=[block.invocation_id, path]).to_dict()
        manifest = block.store.read(ref)
        if not 0 < manifest["size_bytes"] <= limit:
            raise ValueError("Caption evidence exceeds its byte bound")
        frozen = materialize_file(block, ref, path=block.root + "/evidence/" + path)
        return {"path": path, "reference": ref}, manifest, frozen

    batch_file, manifest, frozen = capture(message["frame_batch_ref"], 1024 * 1024)
    batch = json.loads(frozen.read_bytes())
    if not isinstance(batch, dict) or batch.get("schema") != "otterdesk.cctv_operator.frame_batch.v2":
        raise ValueError("Caption batch schema is invalid")
    if any(message[key] != batch.get(key) for key in CLAIM_FIELDS - {"frame_batch_ref", "tick_seq"}):
        raise ValueError("Caption message differs from its admitted batch")
    rows = batch.get("selected_frames")
    if (not isinstance(rows, list) or not 1 <= len(rows) <= max_frames
        or type(batch["selected_count"]) is not int or batch["selected_count"] != len(rows)
        or type(batch["candidate_count"]) is not int or batch["candidate_count"] < len(rows)):
        raise ValueError("Caption frame count differs from its admission policy")
    files, total, prior_time = [batch_file], manifest["size_bytes"], float("-inf")
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("path") != prefix + f"frame-{index:02d}.jpg":
            raise ValueError("Caption selected frame path is invalid")
        timestamp = row.get("timestamp")
        if type(timestamp) not in {int, float} or not math.isfinite(timestamp) or timestamp < prior_time:
            raise ValueError("Caption frames require chronological finite timestamps")
        item, captured, _frozen = capture(row["path"], MAX_BYTES - total)
        if row.get("sha256") != captured["sha256"]:
            raise ValueError("Caption selected frame hash differs from its admission")
        files.append(item)
        total += captured["size_bytes"]
        prior_time = timestamp
    return block.store.commit(block.root + "/caption-evidence.json",
        {"schema": SCHEMA, "scope": _scope(block), "message": message, "files": files},
        kind="cctv_frame_evidence").to_dict()


def publication_writes(block, reference):
    if not isinstance(reference, dict) or reference.get("kind") != "cctv_frame_evidence":
        raise ValueError("Caption evidence requires its committed typed reference")
    evidence = block.store.read(reference)
    if evidence.get("schema") != SCHEMA or evidence.get("scope") != _scope(block):
        raise ValueError("Caption evidence belongs to another camera scope")
    return [ArtifactWrite("frame-evidence-" + str(index), item["path"],
        materialize_file(block, item["reference"], path=block.root + "/evidence/" + item["path"]).read_bytes(),
        kind="frame_batch" if index == 0 else "jpeg", authoritative=True)
        for index, item in enumerate(evidence["files"])]


def read_batch(block, reference, message, *, max_frames):
    """Restore a peer's committed window in a private view, never public names."""
    if (not isinstance(reference, dict) or reference.get("kind") != "cctv_frame_evidence"
        or reference.get("version") != "mn.committed_json/v1"):
        raise ValueError("Vision requires a committed native frame evidence reference")
    evidence = block.store.read(reference)
    if (not isinstance(evidence, dict) or set(evidence) != {"schema", "scope", "message", "files"}
        or evidence["schema"] != SCHEMA or evidence["scope"] != _scope(block)
        or evidence["message"] != {key: value for key, value in message.items() if key != "frame_evidence"}
        or set(evidence["message"]) != CLAIM_FIELDS
        or not isinstance(evidence["files"], list) or not 2 <= len(evidence["files"]) <= max_frames + 1):
        raise ValueError("Vision evidence differs from its camera, run or admitted message")
    batch_id = message["batch_id"]
    if not isinstance(batch_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", batch_id):
        raise ValueError("Vision batch identity is invalid")
    prefix, root = f"frame_batches/{batch_id}/", block.root + "/frame-view/"
    files, total = [], 0
    for index, item in enumerate(evidence["files"]):
        expected = prefix + ("batch.json" if index == 0 else f"frame-{index:02d}.jpg")
        if not isinstance(item, dict) or set(item) != {"path", "reference"} or item["path"] != expected:
            raise ValueError("Vision evidence inventory paths are invalid")
        path = materialize_file(block, item["reference"], path=root + expected)
        total += path.stat().st_size
        if total > MAX_BYTES or (index == 0 and path.stat().st_size > 1024 * 1024):
            raise ValueError("Vision evidence exceeds its byte bound")
        files.append(path)
    batch = json.loads(files[0].read_bytes())
    if (not isinstance(batch, dict) or batch.get("schema") != "otterdesk.cctv_operator.frame_batch.v2"
        or message["frame_batch_ref"] != prefix + "batch.json"
        or any(message[key] != batch.get(key) for key in CLAIM_FIELDS - {"frame_batch_ref", "tick_seq"})
        or not isinstance(batch.get("selected_frames"), list) or len(batch["selected_frames"]) != len(files) - 1
        or type(batch.get("selected_count")) is not int or batch["selected_count"] != len(files) - 1
        or type(batch.get("candidate_count")) is not int or batch["candidate_count"] < len(files) - 1):
        raise ValueError("Vision batch differs from its admitted frame inventory")
    prior_time = float("-inf")
    for row, item in zip(batch["selected_frames"], evidence["files"][1:], strict=True):
        captured = block.store.read(item["reference"])
        timestamp = row.get("timestamp") if isinstance(row, dict) else None
        if (not isinstance(row, dict) or row.get("path") != item["path"] or row.get("sha256") != captured["sha256"]
            or type(timestamp) not in {int, float} or not math.isfinite(timestamp) or timestamp <= 0 or timestamp < prior_time):
            raise ValueError("Vision frame identity or chronological capture time is invalid")
        prior_time = timestamp
    return batch, [path.read_bytes() for path in files[1:]], block.store.path(root.rstrip("/"))
