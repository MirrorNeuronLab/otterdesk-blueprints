from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_DIR = ROOT / "drug_discovery_research_assistant"
STEP_SCRIPTS = {
    "target_discovery": "scripts/stage_a.py",
    "structure_generation": "scripts/stage_b.py",
    "candidate_generation": "scripts/stage_c.py",
    "binding_evaluation": "scripts/stage_d.py",
    "ranking_reporting": "scripts/stage_e.py",
}


def _expand_source_manifest(source: dict) -> dict:
    sdk_root = ROOT.parent / "mn-python-sdk" / "mn_sdk"
    package_spec = importlib.util.spec_from_file_location(
        "mn_sdk",
        sdk_root / "__init__.py",
        submodule_search_locations=[str(sdk_root)],
    )
    package = importlib.util.module_from_spec(package_spec)
    package.__path__ = [str(sdk_root)]
    sys.modules.setdefault("mn_sdk", package)
    profiles_spec = importlib.util.spec_from_file_location(
        "mn_sdk.manifest_profiles",
        sdk_root / "manifest_profiles" / "__init__.py",
        submodule_search_locations=[str(sdk_root / "manifest_profiles")],
    )
    profiles = importlib.util.module_from_spec(profiles_spec)
    assert profiles_spec and profiles_spec.loader
    sys.modules["mn_sdk.manifest_profiles"] = profiles
    profiles_spec.loader.exec_module(profiles)

    spec = importlib.util.spec_from_file_location(
        "mn_sdk.manifest_converter",
        sdk_root / "manifest_converter.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["mn_sdk.manifest_converter"] = module
    spec.loader.exec_module(module)
    return module.expand_manifest_source(source, root_dir=BLUEPRINT_DIR)


def test_drug_discovery_manifest_uses_source_format_and_shared_blocks():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["apiVersion"] == "mn.workflow.source/v1"
    assert manifest["kind"] == "WorkflowSource"
    assert manifest["identity"]["id"] == "drug_discovery_research_assistant"
    assert "nodes" not in manifest.get("agents", {})
    assert "edges" not in manifest.get("agents", {})
    assert [step["id"] for step in manifest["workflow"]["steps"]] == list(STEP_SCRIPTS)
    assert manifest["agents"]["extra_templates"] == [
        {
            "node_id": "report_sink",
            "uses": "mn-agents.control.terminal_sink@1",
            "with": {"stereotype": "terminal_report_sink"},
        }
    ]
    assert manifest["defaults"]["worker"]["with"]["docker_worker_image"] == "worker/docker_worker"
    assert manifest["defaults"]["worker"]["with"]["upload_path"] == "worker"

    by_step = manifest["workers"]["by_step"]
    assert set(by_step) == set(STEP_SCRIPTS)
    for step, script in STEP_SCRIPTS.items():
        assert by_step[step]["with"]["script"] == script


def test_drug_discovery_model_profiles_match_vc_style_defaults():
    config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text(encoding="utf-8"))

    assert config["llm"]["model"] == "gemma4:e2b"
    assert config["llm"]["runtime_model"] == "gemma4:e2b"
    assert config["llm"]["preferred_model"] == "nemotron3"
    assert config["llm"]["configs"]["primary"]["model"] == "gemma4:e2b"
    assert config["llm"]["configs"]["large"]["model"] == "nemotron3"
    assert config["llm"]["small_model_profile"]["runtime_model"] == "gemma4:e2b"
    assert config["llm"]["large_model_profile"]["hardware"]["gpu"] == {
        "min_count": 1,
        "min_memory_mb": 49152,
        "memory_operator": ">=",
    }
    assert {spec["llm_config"] for spec in config["llm"]["agents"].values()} == {"primary"}


def test_drug_discovery_source_manifest_expands_with_stage_scripts_and_terminal_sink():
    source = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))
    expanded = _expand_source_manifest(source)

    node_by_id = {node["node_id"]: node for node in expanded["agents"]["nodes"]}
    assert set(node_by_id) == {*STEP_SCRIPTS, "report_sink"}
    assert any(
        edge["from_node"] == "ranking_reporting"
        and edge["to_node"] == "report_sink"
        and edge["message_type"] == "pipeline_complete"
        for edge in expanded["agents"]["edges"]
    )
    for step, script in STEP_SCRIPTS.items():
        config = node_by_id[step]["config"]
        assert config["command"] == ["/usr/bin/python3.11", script]
        assert config["output_message_type"] == source["workers"]["by_step"][step]["with"]["output_message_type"]
        assert config["docker_worker_image"] == "worker/docker_worker"
        assert config["upload_path"] == "worker"
    assert node_by_id["ranking_reporting"]["config"]["side_effect"] == "internal_write"
    assert node_by_id["report_sink"]["config"]["terminal_sink"] is True
    assert expanded["runtime"]["resources"]["gpu"] == {"min_count": 0}
