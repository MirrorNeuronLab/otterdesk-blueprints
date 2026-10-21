"""Captured research inputs and immutable evidence handoffs."""
import os
from pathlib import Path
from mn_sdk_common.committed_artifacts import validate_embedded_references
from .common import INPUT_KEYS
from .inputs import normalize_inputs


def research_inputs(block, inputs):
    configured = (block.config.get("inputs") or {}).get("payload") or {}
    values = {key: value for key, value in configured.items() if key in INPUT_KEYS}
    values.update({key: value for key, value in inputs.items() if key in INPUT_KEYS and _has_runtime_value(value)})
    return normalize_inputs(values)


def _has_runtime_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value) if isinstance(value, (dict, list, tuple, set)) else True


def read_state(block, previous):
    state = block.store.read(previous["state"])
    validate_embedded_references(block.store, state)
    return state


def save_state(block, state, phase):
    return block.store.commit(f"research/{phase}.json", state, kind="research_evidence").to_dict()


def output_directory(block):
    return Path(os.environ["MN_JOB_OUTPUT_DIR"]) if os.environ.get("MN_JOB_OUTPUT_DIR") else block.store.run_dir
