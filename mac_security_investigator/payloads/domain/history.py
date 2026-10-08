"""Explicit Job-scoped persistence and durable run artifacts."""
import json
from pathlib import Path

from mn_sdk.blueprint_support import write_json
from mn_sdk.step_runtime import artifact_reference
from mn_temporal_graph_skill import EvidenceHistory, fingerprint

from .configuration import investigation_policy


def history(context):
    root = context.get("job_data_dir")
    if not root or not context.get("job_id"):
        raise ValueError("Core-provided Job identity and job-data directory are required")
    policy = investigation_policy()
    scans = read(context, "scan_batch.json")
    if not isinstance(scans, list) or not scans:
        raise ValueError("captured evidence is required")
    epoch = scans[0]["host_epoch_id"]
    if not isinstance(epoch, str) or not epoch or any(s["host_epoch_id"] != epoch for s in scans):
        raise ValueError("one captured host epoch is required")
    # The fingerprint keeps untrusted scan identity out of filesystem paths.
    return EvidenceHistory(Path(root) / "state" / fingerprint(epoch) / "history.sqlite3", epoch,
                           max_records=policy["max_records"], max_bytes=policy["max_scan_bytes"])


def save(context, path, value):
    root = Path(context["run_dir"])
    write_json(root / path, value)
    return artifact_reference(Path(path).stem, path)


def read(context, path):
    return json.loads((Path(context["run_dir"]) / path).read_text())
