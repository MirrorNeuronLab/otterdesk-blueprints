"""Opaque, versioned Harness2 memory snapshots, isolated by the runtime Job."""
import json
from pathlib import Path

from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.artifact_handoff import relative_path
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_sdk_common.files import atomic_write_text

SCHEMA = "otterdesk.harness2.memory.v1"


def validate(snapshot, limits, job_id):
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA
            or snapshot.get("job_id") != job_id
            or type(snapshot.get("generation")) is not int or snapshot["generation"] < 0
            or not isinstance(snapshot.get("files"), dict)):
        raise ValueError("Harness2 memory has an invalid Job identity or generation")
    files = snapshot["files"]
    if len(files) > limits["max_memory_files"]:
        raise ValueError("Harness2 memory file quota exceeded")
    for name, body in files.items():
        relative_path(name)
        if name.split("/")[0] not in {"active", "library"} or not isinstance(body, str):
            raise ValueError("Harness2 memory contains an unsupported entry")
    if len(json.dumps(snapshot, ensure_ascii=False).encode()) > limits["max_memory_bytes"]:
        raise ValueError("Harness2 memory byte quota exceeded")
    return snapshot


def storage(block):
    if not block.job_id or not block.job_data_dir:
        raise ValueError("Runtime Job storage is required for private Harness2 memory")
    root = Path(block.job_data_dir) / "harness_memory"
    if root.is_symlink() or (root / "state.json").is_symlink():
        raise ValueError("Harness2 memory cannot use symlinks")
    root.mkdir(parents=True, exist_ok=True)
    return CommittedJsonStore(root)


def load(block, limits):
    store = storage(block)
    with store.locked("memory"):
        path = store.path("state.json")
        value = json.loads(path.read_text()) if path.exists() else {
            "schema_version": SCHEMA, "job_id": block.job_id,
            "generation": 0, "files": {}, "last_request": None,
        }
        return validate(value, limits, block.job_id)


def adopt(block, snapshot, *, expected_generation, request_id, limits):
    """Compare-and-swap the opaque state; retries never advance memory twice."""
    validate(snapshot, limits, block.job_id)
    if snapshot.get("last_request") != request_id:
        raise ValueError("Harness2 memory does not match the admitted request")
    if snapshot["generation"] != expected_generation + 1:
        raise ValueError("Harness2 returned an unexpected memory generation")
    store = storage(block)
    receipt_path = f"receipts/{request_id}.json"
    digest = fingerprint(snapshot)
    receipt = {"request_id": request_id, "generation": snapshot["generation"], "sha256": digest}
    with store.locked("memory"):
        if store.path(receipt_path).exists():
            if store.read_path(receipt_path) != receipt:
                raise ValueError("A retained Harness2 request changed on replay")
            return receipt
        path = store.path("state.json")
        previous = json.loads(path.read_text()) if path.exists() else {"generation": 0}
        if previous.get("last_request") == request_id:
            if fingerprint(previous) != digest:
                raise ValueError("Retained Harness2 memory differs from the replay")
        else:
            if previous["generation"] != expected_generation:
                raise ValueError("Harness2 memory changed since admission; start a new run")
            atomic_write_text(path, json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")
        store.commit(receipt_path, receipt, kind="harness_memory_receipt")
    return receipt
