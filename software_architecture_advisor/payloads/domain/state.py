"""Frozen repository evidence and phase authority for architecture review."""

import hashlib

from mn_sdk.integrations.block_inputs import capture_declared_inputs
from mn_sdk_common.committed_artifacts import (
    COMMITTED_JSON_VERSION,
    CommittedArtifactRef,
)
from .catalog_store import fingerprint


def request_inputs(block, request):
    return capture_declared_inputs(block, request, runtime_file=__file__)


def freeze_files(block, names):
    files = {}
    for name in sorted(set(names)):
        block.check()
        path = block.store.path(name)
        encoded = path.read_bytes()
        identity = hashlib.sha256(name.encode()).hexdigest()
        digest = hashlib.sha256(encoded).hexdigest()
        target = f"architecture/artifacts/{identity}/{digest}"
        files[name] = block.store.commit_bytes(
            target,
            encoded,
            kind="architecture_evidence",
            **({"version": COMMITTED_JSON_VERSION} if path.suffix == ".json" else {}),
        ).to_dict()
    return files


def save_state(block, phase, *, inputs, files, capture=None):
    state = {
        "version": "architecture.evidence/v1",
        "phase": phase,
        "scope": {"job_id": block.job_id, "run_id": block.run_id},
        "configuration": fingerprint(block.original_config),
        "inputs": inputs,
        "files": files,
    }
    if capture is not None:
        state["capture"] = capture
    return block.store.commit(
        f"architecture/{phase}.json", state, kind="architecture_evidence"
    ).to_dict()


def read_state(block, reference, phase):
    state = block.read_evidence(reference)
    if (
        state.get("version") != "architecture.evidence/v1"
        or state.get("phase") != phase
        or reference.get("path") != f"architecture/{phase}.json"
        or state["scope"] != {"job_id": block.job_id, "run_id": block.run_id}
        or state["configuration"] != fingerprint(block.original_config)
    ):
        raise ValueError(
            "Architecture evidence has different phase, run or configuration"
        )
    for name, ref in state["files"].items():
        block.check()
        if name.startswith("web/") or name == "web_ui.json":
            continue  # Derived shells may be refreshed; frozen JSON remains authoritative.
        actual = block.store.path(name)
        if (
            not actual.is_file()
            or hashlib.sha256(actual.read_bytes()).hexdigest() != ref["sha256"]
        ):
            raise ValueError(
                "Architecture working evidence differs from its frozen capture"
            )
    if phase == "structure":
        read_state(block, state["capture"], "capture")
    return state


def catalog_reference(block, reference, path):
    if reference.get("path") != path:
        raise ValueError("Architecture catalog reference has a different authority")
    ref = CommittedArtifactRef(
        type="artifact_ref",
        version=COMMITTED_JSON_VERSION,
        kind="json",
        path=path,
        sha256=reference["sha256"],
        size_bytes=block.store.path(path).stat().st_size,
    )
    block.store.validate(ref)
    return ref.to_dict()


def bound_structure(block, binding):
    """The owner-only catalog binds source authority without staging its ledger."""
    return read_state(
        block,
        {
            "type": "artifact_ref",
            "version": COMMITTED_JSON_VERSION,
            "kind": "architecture_evidence",
            "path": "architecture/structure.json",
            **binding,
        },
        "structure",
    )
