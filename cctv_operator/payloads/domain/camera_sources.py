"""Accepted cumulative camera Markdown from immutable prior source bytes."""

from datetime import datetime

from mn_sdk_common.publication import ArtifactWrite

from .runtime_memory import CAMERA_MARKDOWN_MAX_BYTES

HEADER = "# Sampled video history\n\nPredictions are hypotheses, not observed events. Demo playback is recorded footage.\n"


def project(block, previous, record):
    observation = record["observation"]
    timestamp = datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00"))
    stem = f"camera-{observation['camera_node_id']}-{timestamp:%Y%m%dT%H}"
    marker = f"<!-- observation:{observation['observation_id']} -->"
    entry = "\n" + marker + "\n" + record["markdown"] + "\n"
    if len((HEADER + entry).encode()) > CAMERA_MARKDOWN_MAX_BYTES:
        raise ValueError("Camera observation exceeds the conversation source limit")
    previous = previous or {}
    part, prior = 1, HEADER
    if previous.get("stem") == stem:
        part = previous["part"]
        prior = block.store.read_bytes(previous["reference"]).decode()
    if marker not in prior:
        if len((prior + entry).encode()) > CAMERA_MARKDOWN_MAX_BYTES:
            part, prior = part + 1, HEADER
        prior += entry
    name = f"context_sources/outputs/{stem}{'' if part == 1 else f'-{part:04d}'}.md"
    content = prior.encode()
    reference = block.store.commit_bytes(block.root + "/camera-source.md", content, kind="cctv_camera_source").to_dict()
    return {"stem": stem, "part": part, "reference": reference}, ArtifactWrite(
        "camera-source", name, content, kind="markdown", authoritative=True)
