from __future__ import annotations

from mn_sdk.bundle_io import load_bundle_payloads

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
    primary_llm = source["llm"]["configs"]["primary"]

    assert source["llm"]["model"] == "default"
    assert source["llm"]["strict_json"] is True
    assert "model" not in primary_llm
    assert "runtime_model" not in primary_llm
    assert primary_llm["max_tokens"] == 10000
    assert source["requirements"]["memory"]["min_gb"] == 2
    assert source["requirements"]["gpu"] == {"min_count": 0}
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


def test_financial_workers_stage_the_domain_package():
    blueprint = ROOT / "financial_advisor"
    expanded = expanded_manifest("financial_advisor")
    executable_nodes = [
        node
        for node in expanded["agents"]["nodes"]
        if (node.get("config") or {}).get("runner_module")
        == "MirrorNeuron.Runner.DockerWorker"
    ]

    assert executable_nodes
    assert all(
        {"source": "domain", "target": "domain"}
        in node["config"]["upload_paths"]
        for node in executable_nodes
    )

    payloads = load_bundle_payloads(blueprint)
    assert "docker_worker/Dockerfile" in payloads


def test_financial_review_normalization_preserves_structured_model_findings():
    result = run_payload_script(
        "financial_advisor",
        """
import json
from domain.review_services import normalize_review_response

finding = {"kind": "source_gap", "source": "sample-w2.txt"}
normalized = normalize_review_response(
    {"risk_flags": [finding, dict(finding)]},
    {
        "summary": "fallback",
        "risk_flags": ["review source evidence"],
        "confidence": 0.68,
    },
    [],
)
print(json.dumps(normalized))
""",
    )

    assert result["risk_flags"] == [
        "review source evidence",
        {"kind": "source_gap", "source": "sample-w2.txt"},
    ]


def test_portfolio_reviewer_does_not_feed_prior_llm_finding_back_to_model():
    result = run_payload_script(
        "financial_advisor",
        """
import json
from domain.portfolio import step_portfolio_llm_reviewer

class CapturingLLM:
    provider = "test"
    model = "test"
    calls = 0
    fallback_calls = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    estimated_tokens = 0

    def generate_json(self, *, user_prompt, fallback, **_kwargs):
        self.calls += 1
        self.user_prompt = user_prompt
        return fallback

llm = CapturingLLM()
ctx = {
    "config": {"llm": {"enabled": True, "configs": {"primary": {}}}},
    "llm": llm,
    "active_knowledge": {},
    "state": {
        "workflow": {
            "portfolio_context_loader": {
                "holding_count": 1,
                "portfolio_source_refs": ["portfolio.json"],
                "risk_policy": {},
                "risk_policy_provenance": {},
                "customer_profile_status": {"missing_fields": []},
            },
            "portfolio_market_data_loader": {
                "provider": "fixture",
                "source_refs": ["fixture:ABC"],
            },
            "portfolio_risk_engine": {
                "total_value": 100.0,
                "cash_weight_pct": 10.0,
                "largest_position_weight_pct": 90.0,
                "largest_position": {"symbol": "ABC", "instrument_type": "stock"},
                "holdings": [{"symbol": "ABC"}],
                "policy_violations": [],
                "screening_threshold_flags": [],
                "warnings": [],
                "actor_finding": {"summary": "PRIOR MODEL NARRATIVE MUST NOT BE RECYCLED"},
            },
        }
    },
}
step_portfolio_llm_reviewer(ctx)
print(json.dumps({"prompt": llm.user_prompt}))
""",
    )

    assert "PRIOR MODEL NARRATIVE MUST NOT BE RECYCLED" not in result["prompt"]
    assert '"total_value": 100.0' in result["prompt"]


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
