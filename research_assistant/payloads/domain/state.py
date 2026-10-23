"""Captured research inputs and immutable evidence handoffs."""
from mn_sdk.integrations.block_inputs import declared_inputs
from .inputs import normalize_inputs


def research_inputs(block, inputs):
    return normalize_inputs(declared_inputs(block, inputs, runtime_file=__file__, omit_empty=True))


def read_state(block, previous):
    state = block.read_evidence(previous["state"])
    return state


def save_state(block, state, phase):
    return block.store.commit(f"research/{phase}.json", state, kind="research_evidence").to_dict()
