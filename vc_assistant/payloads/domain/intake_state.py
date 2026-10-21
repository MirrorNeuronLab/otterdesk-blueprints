"""Scoped VC intake evidence; workflow-state files are derived inspection views."""

from pathlib import Path, PurePosixPath
import os

from mn_sdk.blueprint_support import write_workflow_state
from mn_sdk.integrations.block_files import capture_file, materialize_file
from mn_sdk_common.committed_artifacts import validate_embedded_references

from .intake import _document_paths


def output_directory(block):
    environment = os.environ if block.environment is None else block.environment
    return Path(environment.get("MN_JOB_OUTPUT_DIR") or block.store.run_dir)


def checkpoint_path(role):
    return f"vc/intake/{role}.json"


def prepare_snapshot(block, state, role):
    path = block.root + "/prepared-intake.json"
    receipt = block.root + "/prepared-intake-reference.json"
    if block.store.path(receipt).exists():
        frozen = block.read_checkpoint(block.store.read_path(receipt), expected_path=path)
        def identities(value):
            return [(item["relative_path"], item["artifact"]) for item in value["files"]]
        if identities(frozen) != identities(state):
            raise ValueError("VC intake evidence changed during a pending review")
        return frozen
    state["stage"] = role
    reference = block.commit_checkpoint(path, state)
    block.store.commit(receipt, reference.to_dict(), kind="intake_prepared_receipt")
    return block.read_checkpoint(reference, expected_path=path)


def snapshot_reference(inputs):
    packet = inputs.get("result") or inputs.get("previous")
    if not isinstance(packet, dict) or not isinstance(packet.get("state"), dict):
        raise ValueError("VC intake requires its explicit upstream evidence packet")
    return packet["state"]


def read_snapshot(block, inputs, role):
    state = block.read_checkpoint(snapshot_reference(inputs), expected_path=checkpoint_path(role))
    validate_embedded_references(block.store, state)
    if state.get("stage") != role:
        raise ValueError("VC intake evidence belongs to a different phase")
    return state


def source_inventory(block, folder):
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("VC intake requires a staged document directory")
    result = []
    for path in _document_paths(folder):
        block.check()
        relative = path.relative_to(folder)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != folder.parent):
            raise ValueError("VC document sources cannot contain symlinks")
        reference = capture_file(block, path, key=["vc-input", relative.as_posix()])
        captured = block.store.read(reference)
        result.append({"path": str(path), "relative_path": relative.as_posix(),
                       "suffix": path.suffix.lower(), "size_bytes": captured["size_bytes"],
                       "mtime": path.stat().st_mtime, "sha256": captured["sha256"],
                       "artifact": reference.to_dict()})
        block.check()
    return result


def merge_actor_reviews(state, branches):
    """Merge each verified specialist's own review and inherited qualifications."""
    inherited = list(state.get("actor_review_warnings") or [])
    warnings = list(inherited)
    for role, snapshot in branches.items():
        branch_warnings = snapshot.get("actor_review_warnings") or []
        if branch_warnings[:len(inherited)] != inherited:
            raise ValueError("VC branch changed inherited review warnings")
        warnings.extend(branch_warnings[len(inherited):])
        for key in ("actor_findings", "review_contexts", "memory_witnesses", "observations"):
            if role in snapshot.get(key, {}):
                state.setdefault(key, {})[role] = snapshot[key][role]
    state["actor_review_warnings"] = warnings


def materialize_sources(block, state):
    files = []
    for item in state["files"]:
        path = materialize_file(block, item["artifact"], path="vc/captured-inputs/" + item["relative_path"])
        files.append({**item, "path": str(path)})
    root = block.store.path("vc/captured-inputs")
    root.mkdir(parents=True, exist_ok=True)
    return root, files


def capture_processed_inputs(block, records):
    root = output_directory(block)
    paths = {record["markdown_artifact"]["path"] for values in records.values() for record in values}
    paths.add("context_sources/inputs.json")
    captured = []
    for name in sorted(paths):
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Converted VC inputs must remain in the declared output tree")
        reference = capture_file(block, root / name, key=["vc-processed-input", name])
        captured.append({"path": name, "artifact": reference.to_dict()})
    return captured


def publish_snapshot(block, state, role, outputs, views):
    from .intake_review import review_snapshot

    def produce():
        state["stage"] = role
        review_snapshot(block, state, role)
        from .runtime_tools import observation_records_for_role
        state.setdefault("observations", {})[role] = observation_records_for_role(block.store.run_dir, role)
        return state

    reference = block.freeze_checkpoint(checkpoint_path(role), produce)
    state = block.read_checkpoint(reference, expected_path=checkpoint_path(role))
    # These retain the product's inspectable artifacts while later phases are
    # converted. Native consumers read only the scoped checkpoint above.
    for path, data in views.items():
        write_workflow_state(block.store.run_dir, path, data)
    if "action_ledger" in state:
        write_workflow_state(block.store.run_dir, "action_ledger.json", state["action_ledger"])
    if "actor_findings" in state:
        write_workflow_state(block.store.run_dir, "actor_findings.json", state["actor_findings"])
        write_workflow_state(block.store.run_dir, "actor_review_warnings.json", state.get("actor_review_warnings", []))
    return {**outputs, "state": reference.to_dict()}
