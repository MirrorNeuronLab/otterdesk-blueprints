from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "financial_advisor" / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
HEAVY_STEPS = {
    "tax_workpaper_preparer",
    "portfolio_risk_engine",
    "advisor_review_auditor",
    "financial_advice_reporter",
}


def _load_runner():
    spec = importlib.util.spec_from_file_location("financial_advisor_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeFinancialLLM:
    provider = "fake"
    model = "fake-financial-advisor"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = dict(fallback)
        response["summary"] = response.get("summary") or "Fake advisor review completed."
        response["provider"] = self.provider
        response["model"] = self.model
        return response


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

    return module.expand_manifest_source(source, root_dir=ROOT / "financial_advisor")


def test_financial_advisor_manifest_uses_source_format_and_shared_blocks():
    manifest = json.loads((ROOT / "financial_advisor" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["apiVersion"] == "mn.workflow.source/v1"
    assert manifest["kind"] == "WorkflowSource"
    assert manifest["identity"]["id"] == "financial_advisor"
    assert "nodes" not in manifest.get("agents", {})
    assert "edges" not in manifest.get("agents", {})
    assert [step["id"] for step in manifest["workflow"]["steps"]] == [
        "financial_folder_watcher",
        "financial_document_reader",
        "bank_statement_extractor",
        "cash_flow_normalizer",
        "tax_document_router",
        "tax_workpaper_preparer",
        "portfolio_context_loader",
        "portfolio_market_data_loader",
        "portfolio_risk_engine",
        "public_finance_researcher",
        "advisor_evidence_reconciler",
        "advisor_review_auditor",
        "financial_advice_reporter",
    ]
    assert manifest["agents"]["extra_templates"] == [
        {
            "node_id": "report_sink",
            "uses": "mn-agents.control.terminal_sink@1",
            "with": {"stereotype": "terminal_report_sink"},
        }
    ]
    groups = manifest["workers"]["groups"]
    assert any(group["with"]["stereotype"] == "public_browser_worker" for group in groups)
    assert any(group["with"]["stereotype"] == "internal_write_worker" for group in groups)


def test_financial_advisor_model_profiles_assign_large_to_heavy_nodes():
    config = json.loads((ROOT / "financial_advisor" / "config" / "default.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "financial_advisor" / "manifest.json").read_text(encoding="utf-8"))

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

    by_step = manifest["workers"]["by_step"]
    assert set(by_step) == HEAVY_STEPS
    assert all(item["with"]["llm_config"] == "large" for item in by_step.values())


def test_financial_advisor_source_manifest_expands_with_terminal_sink():
    source = json.loads((ROOT / "financial_advisor" / "manifest.json").read_text(encoding="utf-8"))
    expanded = _expand_source_manifest(source)

    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "report_sink" in node_ids
    assert "financial_advice_reporter" in node_ids
    assert any(
        edge["from_node"] == "financial_advice_reporter" and edge["to_node"] == "report_sink"
        for edge in expanded["agents"]["edges"]
    )
    rendered_reporter = next(node for node in expanded["agents"]["nodes"] if node["node_id"] == "financial_advice_reporter")
    assert rendered_reporter["config"]["llm_config"] == "large"
    assert rendered_reporter["config"]["environment"]["MN_LLM_CONFIG"] == "large"
    assert expanded["runtime"]["resources"]["gpu"] == {"min_count": 0}


def test_financial_advisor_smoke_run_writes_integrated_artifacts(tmp_path):
    runner = _load_runner()
    llm = FakeFinancialLLM()
    output_folder = tmp_path / "out"
    result = runner.run_blueprint(
        inputs={
            "document_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "input_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "output_folder": str(output_folder),
        },
        runs_root=tmp_path / "runs",
        run_id="financial-advisor-test",
        llm_client=llm,
    )

    assert result["blueprint_id"] == "financial_advisor"
    artifact = result["final_artifact"]
    assert artifact["type"] == "financial_advisor_report"
    assert artifact["bank_statement_extraction"]["statement_count"] == 1
    assert artifact["bank_statement_extraction"]["totals"]["deposits"] > 0
    assert artifact["household_finance_summary"]["income_total"] > 0
    assert artifact["tax_review_packet"]["workpapers"]["draft_income_total"] > 0
    assert artifact["portfolio_risk_review"]["total_value"] > 0
    assert artifact["model_profiles_used"]["financial_advice_reporter"]["llm_config"] == "large"
    assert (tmp_path / "runs" / "financial-advisor-test" / "final_artifact.json").exists()
    assert (output_folder / "financial_advisor_report.md").exists()
    assert (output_folder / "bank_statement_extraction.json").exists()
    assert "review-only" in (output_folder / "financial_advisor_report.md").read_text(encoding="utf-8")
