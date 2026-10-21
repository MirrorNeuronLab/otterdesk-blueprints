"""OpenShell stays optional; selected catalog block workers share one transport."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from mn_sdk.artifact_handoff import validate_configuration
from mn_sdk.blueprints.worker_descriptors import stage_worker_descriptor_uploads

from blueprint_modernization_support import expanded_manifest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "index.json").read_text())
SHARED_HANDLERS = {
    "mn_sdk.integrations.block_worker",
    "mn_sdk.integrations.block_auxiliary",
}


@pytest.mark.parametrize("blueprint", CATALOG)
def test_selected_openshell_workers_use_standard_sdk_core_handoff(blueprint):
    compiled = expanded_manifest(blueprint)
    nodes = compiled["agents"]["nodes"]
    selected = []
    for node in nodes:
        config = node.get("config", {})
        if config.get("runner_module") != "MirrorNeuron.Runner.OpenShell":
            continue
        selected.append(node)
        assert config["environment"]["MN_WORKFLOW_STEP_HANDLER"] in SHARED_HANDLERS
        assert config["artifact_handoff"]["version"] == "mn.artifact_handoff/v1"
        assert config.get("sync_shared_storage") is not True
        assert config.get("policy")
    if blueprint == "software_architecture_advisor":
        assert selected


@pytest.mark.parametrize("blueprint", CATALOG)
def test_catalog_block_workers_can_opt_into_shared_openshell_transport(blueprint):
    original = expanded_manifest(blueprint)
    selected = deepcopy(original)
    workers = [
        node for node in selected["agents"]["nodes"]
        if node.get("config", {}).get("environment", {}).get("MN_WORKFLOW_STEP_HANDLER")
        in SHARED_HANDLERS
    ]
    assert any(
        node.get("config", {}).get("environment", {}).get("MN_WORKFLOW_STEP_HANDLER", "")
        .startswith("mn_sdk.integrations.block_")
        for node in selected["agents"]["nodes"]
    )
    # Native/device nodes retain their own runners. Auxiliary services share the
    # same worker transport while keeping their declared lifecycle semantics.
    bindings = [deepcopy(node["config"]["environment"]) for node in workers]
    for node in workers:
        config = node["config"]
        config["runner_module"] = "MirrorNeuron.Runner.OpenShell"
        config.pop("artifact_handoff", None)
        config.pop("sync_shared_storage", None)
        with pytest.raises(ValueError, match="require artifact_handoff"):
            validate_configuration(config)
        config["artifact_handoff"] = {"version": "mn.artifact_handoff/v1"}
        config["reuse_shared_sandbox"] = True
        validate_configuration(config)

    # Selection retains each real compiled hook/lock and stages its descriptor.
    # Images, permissions and device access still require a suitable worker policy.
    stage_worker_descriptor_uploads(selected, {})
    for node, binding in zip(workers, bindings, strict=True):
        config = node["config"]
        assert config["environment"] == binding
        assert any(
            {"source": path, "target": path} in config["upload_paths"]
            for path in (".", "runtime", "runtime/manifest.json")
        )
    assert selected["workflow"] == original["workflow"]
    assert selected["metadata"] == original["metadata"]
