from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_DIR = ROOT / "personal_legal_assistant"
RUNNER_PATH = BLUEPRINT_DIR / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
HEAVY_STEPS = {
    "contract_playbook_comparator",
    "legal_review_auditor",
    "personal_legal_reporter",
}
WORKFLOW_STEPS = [
    "legal_folder_watcher",
    "legal_document_reader",
    "invoice_bill_extractor",
    "payable_field_validator",
    "contract_clause_extractor",
    "contract_playbook_comparator",
    "legal_evidence_reconciler",
    "legal_review_auditor",
    "personal_legal_reporter",
]


def _load_runner():
    spec = importlib.util.spec_from_file_location("personal_legal_assistant_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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


class FakeLegalLLM:
    provider = "fake"
    model = "fake-personal-legal"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        response = dict(fallback)
        response["summary"] = response.get("summary") or "Fake legal review completed."
        response["provider"] = self.provider
        response["model"] = self.model
        return response


def test_personal_legal_manifest_uses_source_format_and_shared_blocks():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["apiVersion"] == "mn.workflow.source/v1"
    assert manifest["kind"] == "WorkflowSource"
    assert manifest["identity"]["id"] == "personal_legal_assistant"
    assert "nodes" not in manifest.get("agents", {})
    assert "edges" not in manifest.get("agents", {})
    assert [step["id"] for step in manifest["workflow"]["steps"]] == WORKFLOW_STEPS
    assert manifest["agents"]["extra_templates"] == [
        {
            "node_id": "report_sink",
            "uses": "mn-agents.control.terminal_sink@1",
            "with": {"stereotype": "terminal_report_sink"},
        }
    ]
    groups = manifest["workers"]["groups"]
    assert any(group["with"]["stereotype"] == "internal_write_worker" for group in groups)


def test_personal_legal_model_profiles_assign_large_to_heavy_nodes():
    config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text(encoding="utf-8"))
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert config["llm"]["model"] == "gemma4:e2b"
    assert config["llm"]["runtime_model"] == "gemma4:e2b"
    assert config["llm"]["preferred_model"] == "nemotron3"
    assert config["llm"]["configs"]["primary"]["model"] == "gemma4:e2b"
    assert config["llm"]["configs"]["large"]["model"] == "nemotron3"
    assert config["llm"]["large_model_profile"]["hardware"]["gpu"] == {
        "min_count": 1,
        "min_memory_mb": 49152,
        "memory_operator": ">=",
    }
    for step, spec in config["llm"]["agents"].items():
        expected = "large" if step in HEAVY_STEPS else "primary"
        assert spec["llm_config"] == expected, step

    assert set(manifest["workers"]["by_step"]) == HEAVY_STEPS
    assert all(item["with"]["llm_config"] == "large" for item in manifest["workers"]["by_step"].values())


def test_personal_legal_source_manifest_expands_with_terminal_sink():
    source = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))
    expanded = _expand_source_manifest(source)

    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "report_sink" in node_ids
    assert "personal_legal_reporter" in node_ids
    assert any(
        edge["from_node"] == "personal_legal_reporter" and edge["to_node"] == "report_sink"
        for edge in expanded["agents"]["edges"]
    )
    rendered_reporter = next(node for node in expanded["agents"]["nodes"] if node["node_id"] == "personal_legal_reporter")
    assert rendered_reporter["config"]["llm_config"] == "large"
    assert rendered_reporter["config"]["environment"]["MN_LLM_CONFIG"] == "large"
    assert expanded["runtime"]["resources"]["gpu"] == {"min_count": 0}


def test_personal_legal_smoke_run_writes_merged_artifacts(tmp_path):
    runner = _load_runner()
    llm = FakeLegalLLM()
    output_folder = tmp_path / "out"
    result = runner.run_blueprint(
        inputs={
            "document_folder": str(BLUEPRINT_DIR / "examples" / "sample_inputs"),
            "input_folder": str(BLUEPRINT_DIR / "examples" / "sample_inputs"),
            "output_folder": str(output_folder),
        },
        runs_root=tmp_path / "runs",
        run_id="personal-legal-test",
        llm_client=llm,
    )

    assert result["blueprint_id"] == "personal_legal_assistant"
    artifact = result["final_artifact"]
    assert artifact["type"] == "personal_legal_assistant_report"
    assert artifact["invoice_bill_extraction"]["invoice_count"] == 1
    assert artifact["invoice_bill_extraction"]["totals"]["total_amount"] == 1842.66
    assert artifact["contract_clause_review"]["contract_count"] == 1
    assert artifact["contract_clause_review"]["clause_count"] >= 5
    assert artifact["model_profiles_used"]["personal_legal_reporter"]["llm_config"] == "large"
    assert (tmp_path / "runs" / "personal-legal-test" / "final_artifact.json").exists()
    assert (output_folder / "personal_legal_report.md").exists()
    assert (output_folder / "invoice_bill_extraction.json").exists()
    assert (output_folder / "contract_clause_review.json").exists()
