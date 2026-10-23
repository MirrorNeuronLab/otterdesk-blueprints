"""Immutable procurement evidence handoffs between the two Core branches."""
from mn_sdk.blueprint_support import BlueprintBundleLayout
from mn_sdk.integrations.block_inputs import declared_inputs
from .inputs import normalize_inputs


def bundle_layout():
    return BlueprintBundleLayout.discover(__file__)


def purchase_inputs(block, inputs):
    return normalize_inputs(declared_inputs(block, inputs, runtime_file=__file__))


def read_state(block, previous):
    state = block.read_evidence(previous["state"])
    return state


def save_state(block, state, phase):
    return block.store.commit(f"procurement/{phase}.json", state, kind="procurement_evidence").to_dict()
