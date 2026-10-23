"""Immutable financial evidence packets between the ordered Core specialists."""
from pathlib import Path
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.integrations.block_inputs import declared_inputs
from .common import _SOURCE_MANIFEST

INPUT_KEYS = frozenset(_SOURCE_MANIFEST["contracts"]["inputs"])


def finance_inputs(block, request):
    values = declared_inputs(block, request, runtime_file=__file__)
    folder = values.get("document_folder") or values.get("input_folder")
    if not folder:
        raise ValueError("Financial review requires a staged document folder")
    if not Path(folder).is_dir():
        raise ValueError("Financial review requires a document directory")
    return values


def read_state(block, previous):
    state = block.read_evidence(previous["state"])
    if state["configuration"] != fingerprint(block.config):
        raise ValueError("Financial evidence was captured under different configuration")
    return state


def save_result(block, state, role, result):
    block.check()
    state["workflow"][role] = result
    from .review_services import step_model_profile
    profile = step_model_profile(block.config, role)
    state.setdefault("model_profiles_used", {})[role] = {key: profile[key] for key in ("llm_config", "model", "runtime_model")}
    reference = block.store.commit(f"financial/{role}.json", state, kind="financial_evidence")
    return {"status": "completed", "state": reference.to_dict()}
