"""Case evidence authority across native source and index phases."""

from mn_sdk.artifacts import file_sha256
from mn_sdk_common.committed_artifacts import COMMITTED_JSON_VERSION


def json_reference(block, name, *, kind="case_evidence"):
    return block.store.commit_bytes(name, block.store.path(name).read_bytes(),
        kind=kind, version=COMMITTED_JSON_VERSION).to_dict()


def seal(block, phase, value):
    return block.commit_checkpoint(f"case/{phase}.json", value).to_dict()


def read_seal(block, reference, phase):
    return block.read_checkpoint(reference, expected_path=f"case/{phase}.json")


def capture(block, inputs):
    payload = dict(inputs)
    names = ["source_inventory.json", "matter.json", "handling.json", "review_plan.json", "source-query.json"]
    if inputs.get("review_file"):
        from pathlib import Path
        selected = Path(inputs["review_file"])
        if selected.is_symlink() or not selected.is_file() or selected.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Review file must be a bounded regular JSON file")
        with selected.open("rb") as stream:
            encoded = stream.read(2 * 1024 * 1024 + 1)
        if len(encoded) > 2 * 1024 * 1024:
            raise ValueError("Review file exceeds its byte limit")
        import json
        json.loads(encoded)
        reference = block.store.commit_bytes("case/review-input.json", encoded,
            kind="case_review_import", version=COMMITTED_JSON_VERSION)
        payload["review_file"] = str(block.store.path(reference.path))
        names.append("review-input.json")
    return seal(block, "capture", {"request": inputs, "inputs": payload,
        "files": {name: json_reference(block, "case/" + name) for name in names}})


def read_capture(block, reference):
    value = read_seal(block, reference, "capture")
    for name, ref in value["files"].items():
        if ref.get("path") != "case/" + name:
            raise ValueError("Case capture artifact binding changed")
        block.store.validate(ref)
    inventory = block.store.read(value["files"]["source_inventory.json"])
    if file_sha256(block.store.path("case/sources.json")) != inventory["sources_sha256"]:
        raise ValueError("prepared source snapshot hash mismatch")
    for entry in inventory["files"]:
        block.check()
        original = block.store.path("case/originals/" + entry["sha256"])
        if original.stat().st_size != entry["size_bytes"] or file_sha256(original) != entry["sha256"]:
            raise ValueError("Original case evidence hash mismatch")
    return value


def capture_result(block, reference):
    value = read_capture(block, reference)
    inventory = block.store.read(value["files"]["source_inventory.json"])
    return {"evidence": reference, "source_inventory": value["files"]["source_inventory.json"],
        "document_count": inventory["document_count"], "unreadable_count": len(inventory["unreadable_sources"])}


def indexed(block, capture_reference):
    return seal(block, "indexed", {"capture": capture_reference,
        "index_receipt": json_reference(block, "case/indexes.json")})


def read_indexed(block, reference):
    value = read_seal(block, reference, "indexed")
    capture_state = read_capture(block, value["capture"])
    if value["index_receipt"].get("path") != "case/indexes.json":
        raise ValueError("Case index receipt binding changed")
    block.store.validate(value["index_receipt"])
    from .indexing import validate_indexes
    validate_indexes(block.store.run_dir / "case", block.original_config["investigation"]["access_scope"])
    return value, capture_state


def file_record(block, name):
    path = block.store.path(name)
    if not path.is_file():
        raise ValueError("Case artifact is not a regular file")
    return {"path": name, "sha256": file_sha256(path), "size_bytes": path.stat().st_size}


def verify_files(block, files):
    for item in files:
        block.check()
        if file_record(block, item["path"]) != item:
            raise ValueError("Case artifact hash mismatch")


def terminal(block, indexed, inputs, state, summary, **extra):
    if block.store.path("case/terminal.json").exists():
        reference = json_reference(block, "case/terminal.json", kind="block_checkpoint")
        existing = read_terminal(block, {"terminal": reference})
        expected = {"indexed": indexed, "inputs": inputs, "stop_reason": state["stop_reason"], **extra}
        if any(existing.get(key) != value for key, value in expected.items()):
            raise ValueError("Case terminal decision changed")
        return terminal_result(reference, existing)
    from mn_sdk.blueprint_support import write_json
    from .evidence.store import EvidenceStore
    from .models import DraftReport
    EvidenceStore(block.store.path("case/evidence.sqlite3")).save_agent_review(
        DraftReport(**summary["report"]), list(state["data"]["hypotheses"].values()))
    write_json(block.store.path("case/agent_checkpoint.json"), state)
    write_json(block.store.path("case/investigation.json"), summary)
    checkpoint = file_record(block, "case/agent_checkpoint.json")
    investigation = file_record(block, "case/investigation.json")
    reason = state["stop_reason"]
    audit = file_record(block, "case/evidence.sqlite3")
    reference = seal(block, "terminal", {"indexed": indexed, "inputs": inputs,
        "checkpoint": checkpoint, "investigation": investigation,
        "audit_database": audit, "stop_reason": reason, **extra})
    return terminal_result(reference, {"investigation": investigation, "audit_database": audit, "stop_reason": reason})


def terminal_result(reference, value):
    return {"terminal": reference, **{key: value[key] for key in ("investigation", "audit_database", "stop_reason")}}


def read_terminal(block, result):
    value = read_seal(block, result["terminal"], "terminal")
    _, captured = read_indexed(block, value["indexed"])
    if value["inputs"] != captured["inputs"]:
        raise ValueError("Terminal case source selection changed")
    for key, name in (("checkpoint", "agent_checkpoint.json"), ("investigation", "investigation.json"), ("audit_database", "evidence.sqlite3")):
        if value[key].get("path") != "case/" + name:
            raise ValueError("Case terminal artifact binding changed")
    verify_files(block, [value["checkpoint"], value["investigation"], value["audit_database"]])
    return value
