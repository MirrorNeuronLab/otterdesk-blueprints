from __future__ import annotations

from blueprint_modernization_support import (
    ROOT,
    assert_modular_payload,
    assert_registry_handlers_import,
    expanded_manifest,
    run_payload_script,
    source_manifest,
)


EXPECTED_STEPS = [
    "prepare_financial_packet",
    "analyze_household_finances",
    "prepare_tax_review",
    "analyze_portfolio_risk",
    "collect_public_finance_guidance",
    "reconcile_advisor_evidence",
    "publish_financial_review_packet",
]


def test_financial_manifest_compiles_ordered_regulated_state_pipeline():
    source = source_manifest("financial_advisor")
    expanded = expanded_manifest("financial_advisor")
    assert [step["id"] for step in source["workflow"]["steps"]] == EXPECTED_STEPS
    assert [step.get("needs", []) for step in source["workflow"]["steps"]] == [
        [],
        ["prepare_financial_packet"],
        ["analyze_household_finances"],
        ["prepare_tax_review"],
        ["analyze_portfolio_risk"],
        ["collect_public_finance_guidance"],
        ["reconcile_advisor_evidence"],
    ]
    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "prepare_tax_review__capture" in node_ids
    assert "analyze_portfolio_risk__risk" in node_ids
    assert "publish_financial_review_packet__end" in node_ids


def test_financial_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("financial_advisor")
    assert_registry_handlers_import("financial_advisor")
    execution = (ROOT / "financial_advisor" / "payloads" / "domain" / "execution.py").read_text()
    assert "workflow_step_id" not in execution
    assert "WORKFLOW_STEPS[-1]" not in execution


def test_financial_sample_builds_customer_and_audit_layers(tmp_path):
    result = run_payload_script(
        "financial_advisor",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

root = Path({str((ROOT / 'financial_advisor').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
run = run_blueprint(
    inputs={{"document_folder": str(root / "examples" / "sample_inputs"), "input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out), "quick_test": True}},
    config={{"execution": {{"quick_test": True}}}},
    runs_root=out / "runs",
    run_id="financial-quality",
)
artifact = run["final_artifact"]
print(json.dumps({{
    "status": run["status"],
    "cash_flow": artifact["household_finance_summary"]["preliminary_net_cash_flow"],
    "draft_income": artifact["tax_review_packet"]["workpapers"]["draft_income_total"],
    "portfolio_value": artifact["portfolio_risk_review"]["total_value"],
    "profile_status": artifact["portfolio_risk_review"]["suitability_assessment"]["status"],
    "portfolio_readiness": artifact["customer_readiness"]["portfolio"],
    "top_priority": artifact["customer_report"]["top_actions"][0]["priority"],
    "top_action": artifact["customer_report"]["top_actions"][0]["customer_action"],
    "run_artifact_exists": (out / "runs" / "financial-quality" / "final_artifact.json").exists(),
    "customer_report_exists": (out / "customer_report.json").exists(),
}}))
""",
    )
    assert result["status"] == "completed"
    assert result["cash_flow"] == 2394.8599999999997
    assert result["draft_income"] == 88528.44
    assert result["portfolio_value"] == 186000.0
    assert result["profile_status"] == "complete"
    assert "objectives were supplied" in result["portfolio_readiness"]["label"]
    assert "fixture prices" in result["portfolio_readiness"]["label"]
    assert result["top_priority"] == "Critical"
    assert "Schedule E" in result["top_action"]
    assert result["run_artifact_exists"] is True
    assert result["customer_report_exists"] is True
