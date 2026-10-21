"""Immutable procurement evidence handoffs between the two Core branches."""
import os
from pathlib import Path
from mn_sdk.blueprint_support import BlueprintBundleLayout
from mn_sdk_common.committed_artifacts import validate_embedded_references
from .inputs import normalize_inputs
from .common import INPUT_KEYS


def bundle_layout():
    return BlueprintBundleLayout.discover(__file__)


def purchase_inputs(block, inputs):
    values = {key: value for key, value in ((block.config.get("inputs") or {}).get("payload") or {}).items() if key in INPUT_KEYS}
    values.update({key: value for key, value in inputs.items() if key in INPUT_KEYS and value is not None})
    return normalize_inputs(values)


def read_state(block, previous):
    state = block.store.read(previous["state"])
    validate_embedded_references(block.store, state)
    return state


def save_state(block, state, phase):
    return block.store.commit(f"procurement/{phase}.json", state, kind="procurement_evidence").to_dict()


def output_directory(block):
    return Path(os.environ["MN_JOB_OUTPUT_DIR"]) if os.environ.get("MN_JOB_OUTPUT_DIR") else block.store.run_dir
