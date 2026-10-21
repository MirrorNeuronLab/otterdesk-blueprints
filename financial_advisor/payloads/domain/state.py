"""Immutable financial evidence packets between the ordered Core specialists."""
import os
from pathlib import Path
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.blueprint_support import BlueprintBundleLayout, expand_runtime_path
from mn_sdk_common.committed_artifacts import validate_embedded_references
from .common import _SOURCE_MANIFEST

INPUT_KEYS = frozenset(_SOURCE_MANIFEST["contracts"]["inputs"])


def finance_inputs(block, request):
    values = {key: value for key, value in ((block.config.get("inputs") or {}).get("payload") or {}).items() if key in INPUT_KEYS}
    values.update({key: value for key, value in request.items() if key in INPUT_KEYS and value is not None})
    raw = next((value for value in (request.get("document_folder"), request.get("input_folder"))
        if str(value or "").strip() not in {"", "."}), (block.config.get("document_sources") or {}).get("folder_path"))
    if not raw:
        raise ValueError("Financial review requires a staged document folder")
    path = expand_runtime_path(raw)
    if not path.is_absolute():
        path = Path(os.environ.get("MN_WORKDIR") or BlueprintBundleLayout.discover(__file__).runtime_dir) / path
    values["document_folder"] = values["input_folder"] = str(path.resolve(strict=True))
    if not path.is_dir():
        raise ValueError("Financial review requires a document directory")
    return values


def read_state(block, previous):
    state = block.store.read(previous["state"])
    validate_embedded_references(block.store, state)
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


def output_directory(block):
    return Path(os.environ["MN_JOB_OUTPUT_DIR"]) if os.environ.get("MN_JOB_OUTPUT_DIR") else block.store.run_dir
