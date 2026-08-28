from __future__ import annotations

import json

from mn_sdk.blueprint_runtime import load_blueprint_config
from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads
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
    "frame_purchase_request",
    "build_purchase_evidence",
    "compare_purchase_options",
    "audit_purchase_recommendation",
    "publish_purchase_decision_packet",
]


def test_purchasing_manager_manifest_compiles_logical_steps_and_specialist_graphs():
    source = source_manifest("purchasing_manager")
    expanded = expanded_manifest("purchasing_manager")
    assert source["apiVersion"] == "mn.workflow/v1"
    assert [step["id"] for step in source["workflow"]["steps"]] == EXPECTED_STEPS
    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "compare_purchase_options__market" in node_ids
    assert "compare_purchase_options__cost" in node_ids
    assert "compare_purchase_options__risk" in node_ids
    assert "audit_purchase_recommendation__purchase_recommendation_auditor" in node_ids
    assert "audit_purchase_recommendation__end" in node_ids
    assert "publish_purchase_decision_packet__end" in node_ids


def test_purchasing_manager_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("purchasing_manager")
    assert_registry_handlers_import("purchasing_manager")


def test_purchasing_manager_compiled_docker_workers_ship_their_build_context():
    blueprint = ROOT / "purchasing_manager"
    expanded = expanded_manifest("purchasing_manager")
    worker_nodes = [
        node
        for node in expanded["agents"]["nodes"]
        if (node.get("config") or {}).get("runner_module")
        == "MirrorNeuron.Runner.DockerWorker"
    ]
    assert worker_nodes
    assert {
        node["config"]["docker_worker_image"]
        for node in worker_nodes
    } == {"docker_worker"}
    assert all(
        {"source": "domain", "target": "domain"}
        in node["config"]["upload_paths"]
        for node in worker_nodes
    )

    payloads = load_bundle_payloads(blueprint)
    assert "docker_worker/Dockerfile" in payloads


def test_purchasing_manager_sample_produces_a_procurement_ready_ai_workstation_comparison(tmp_path):
    result = run_payload_script(
        "purchasing_manager",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint
from domain.inputs import parse_plain_text_purchase_request

root = Path({str((ROOT / 'purchasing_manager').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
run = run_blueprint(
    inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out)}},
    config={{"execution": {{"quick_test": True}}}},
    runs_root=out / "runs",
    run_id="purchase-quality",
)
artifact = run["final_artifact"]
comparisons = artifact["candidate_comparisons"]
parsed_request = parse_plain_text_purchase_request(
    (root / "examples" / "sample_inputs" / "purchase_request.txt").read_text()
)
report = (out / "purchasing_manager_report.md").read_text()
print(json.dumps({{
    "status": run["status"],
    "action": artifact["recommended_action"],
    "preferred": artifact["preferred_candidate"],
    "candidate_count": len(comparisons),
    "matching_count": sum(1 for item in comparisons if item["hard_constraints_passed"]),
    "preferred_landed_cost": comparisons[0]["tco"]["landed_acquisition_cost"],
    "preferred_financial_npv": comparisons[0]["tco"]["financial_npv_tco"],
    "preferred_risk_npv": comparisons[0]["tco"]["risk_adjusted_npv_tco"],
    "preferred_eac": comparisons[0]["tco"]["equivalent_annual_cost"],
    "preferred_cost_per_hour": comparisons[0]["tco"]["risk_adjusted_cost_per_productive_hour"],
    "scenario_low": artifact["procurement_summary"]["scenario_risk_adjusted_npv_low"],
    "scenario_high": artifact["procurement_summary"]["scenario_risk_adjusted_npv_high"],
    "scenario_count": len(comparisons[0]["scenario_analysis"]),
    "method_statuses": {{item["method"]: item["status"] for item in comparisons[0]["acquisition_method_analysis"]}},
    "dell_over_budget": comparisons[1]["hard_constraint_checks"]["budget"] is False,
    "bh_unavailable": comparisons[2]["hard_constraint_checks"]["available_for_purchase_required"] is False,
    "preferred_source_url": comparisons[0]["source_url"],
    "gap_count": len(artifact["evidence_gaps"]),
    "rag_status": artifact["knowledge_rag"]["status"],
    "run_artifact_exists": (out / "runs" / "purchase-quality" / "final_artifact.json").exists(),
    "report_exists": (out / "purchasing_manager_report.md").exists(),
    "purchase_type": artifact["purchase_type"],
    "item_description": artifact["item_description"],
    "request_source_ref": artifact["request_source"]["source_ref"],
    "research_lead_count": len(artifact["research_leads"]),
    "parsed_constraints": parsed_request["constraints"],
    "budget_status": artifact["procurement_summary"]["budget_status"],
    "decision_status": artifact["procurement_summary"]["decision_status"],
    "approval_count": len(artifact["procurement_summary"]["approval_checklist"]),
    "preferred_warranty": comparisons[0]["warranty_years"],
    "report_has_decision_summary": "## Procurement Decision Summary" in report,
    "report_has_comparison_table": "| Option | Supplier | Observed price | Landed cost |" in report,
    "report_has_lifecycle_analysis": "## Preferred Option Lifecycle Cost Analysis" in report,
    "report_has_scenarios": "### Scenario Sensitivity" in report,
    "report_has_acquisition_methods": "### Acquisition Funding Method Analysis" in report,
    "report_has_approval_checklist": "## Approval Checklist" in report,
}}))
""",
    )
    assert result == {
        "status": "completed",
        "action": "consider",
        "preferred": "microcenter-powerspec-g913",
        "candidate_count": 3,
        "matching_count": 1,
        "preferred_landed_cost": 4501.23,
        "preferred_financial_npv": 5019.07,
        "preferred_risk_npv": 7956.96,
        "preferred_eac": 3087.57,
        "preferred_cost_per_hour": 2.65,
        "scenario_low": 5622.35,
        "scenario_high": 13559.83,
        "scenario_count": 3,
        "method_statuses": {
            "cash": "modeled",
            "finance": "not_modeled_missing_terms",
            "lease": "not_modeled_missing_terms",
        },
        "dell_over_budget": True,
        "bh_unavailable": True,
        "preferred_source_url": "https://www.microcenter.com/product/700439/powerspec-g913-gaming-pc?storeid=121",
        "gap_count": 5,
        "rag_status": "skipped_quick_test",
        "run_artifact_exists": True,
        "report_exists": True,
        "purchase_type": "computer",
        "item_description": "Source one supportable local-AI desktop for the Boston engineering office. Two machine-learning engineers will use it for private model prototyping, document-extraction evaluation, retrieval experiments, and smaller fine-tuning jobs. We need a complete desktop system, not a DIY parts list or a cloud subscription.",
        "request_source_ref": "local:purchase_request.txt",
        "research_lead_count": 10,
        "parsed_constraints": {
            "min_gpu_vram_gb": 16,
            "min_system_ram_gb": 64,
            "min_storage_tb": 2,
            "min_warranty_years": 1,
            "available_for_purchase_required": True,
        },
        "budget_status": "within_budget",
        "decision_status": "source_refresh_and_human_approval_required",
        "approval_count": 7,
        "preferred_warranty": 1,
        "report_has_decision_summary": True,
        "report_has_comparison_table": True,
        "report_has_lifecycle_analysis": True,
        "report_has_scenarios": True,
        "report_has_acquisition_methods": True,
        "report_has_approval_checklist": True,
    }


def test_purchasing_manager_models_real_finance_and_lease_terms_when_supplied():
    result = run_payload_script(
        "purchasing_manager",
        """
import json
from domain.comparison import build_candidate_comparisons

documents = [{
    "suffix": ".json",
    "source_ref": "local:approved_term_sheet.json",
    "text": json.dumps({
        "candidates": [{
            "candidate_id": "approved-heavy-asset-offer",
            "vendor": "Approved Supplier",
            "source_type": "written_supplier_quote",
            "source_url": "https://supplier.example/quote-reference",
            "observed_at": "2026-08-28",
            "quote_subtotal": 100000,
            "available_for_purchase": True,
            "warranty_years": 3,
            "acquisition_methods": [
                {"method": "finance", "annual_percentage_rate": 0.06, "term_months": 60, "down_payment": 10000, "fees": 1000},
                {"method": "lease", "monthly_payment": 2000, "term_months": 60, "down_payment": 0, "fees": 500, "buyout_cost": 10000},
            ],
        }]
    }),
}]
comparison = build_candidate_comparisons(
    {
        "purchase_type": "computer",
        "budget": 125000,
        "constraints": {"available_for_purchase_required": True},
        "analysis": {"horizon_years": 5, "discount_rate": 0.08},
    },
    documents,
)[0]
methods = {item["method"]: item for item in comparison["acquisition_method_analysis"]}
print(json.dumps({
    "cash": methods["cash"],
    "finance": methods["finance"],
    "lease": methods["lease"],
}))
""",
    )
    assert result["cash"] == {
        "method": "cash",
        "status": "modeled",
        "nominal_cash_outflow": 100000.0,
        "present_value_cost": 100000.0,
        "incremental_present_value_vs_cash": 0.0,
    }
    assert result["finance"]["status"] == "modeled"
    assert result["finance"]["monthly_payment"] == 1739.95
    assert result["finance"]["nominal_cash_outflow"] == 115397.13
    assert result["finance"]["present_value_cost"] == 96811.71
    assert result["finance"]["incremental_present_value_vs_cash"] == -3188.29
    assert result["lease"]["status"] == "modeled"
    assert result["lease"]["nominal_cash_outflow"] == 130500.0
    assert result["lease"]["present_value_cost"] == 105848.97
    assert result["lease"]["incremental_present_value_vs_cash"] == 5848.97


def test_purchasing_manager_config_uses_bundle_paths_and_manifest_owned_descriptors():
    config = json.loads((ROOT / "purchasing_manager" / "config" / "default.json").read_text())
    manifest = json.loads((ROOT / "purchasing_manager" / "manifest.json").read_text())
    assert config["inputs"]["payload"]["input_folder"] == "@/examples/sample_inputs"
    assert config["inputs"]["adapter"] == "json"
    assert config["mode"] == "live"
    assert config["inputs"]["payload"]["analysis"]["discount_rate"] == 0.08
    assert len(config["inputs"]["payload"]["analysis"]["scenarios"]) == 3
    assert config["internet_research"] == {
        "enabled": True,
        "max_seed_urls": 6,
        "max_queries": 2,
        "max_sources": 3,
        "min_observed_sources_before_search": 4,
        "search_only_when_source_gap": True,
        "timeout_seconds": 12,
        "total_timeout_seconds": 30,
        "max_chars": 12000,
        "respect_robots": True,
        "per_host_delay_seconds": 1,
    }
    assert "identity" not in config
    assert "agents" not in config["llm"]
    assert config["budgets"]["max_llm_calls"] == 5
    assert config["llm"]["strict_json"] is True
    assert config["llm"]["require_live"] is False
    assert config["llm_analysis"] == {
        "max_calls_per_run": 5,
        "max_context_chars": 30000,
        "max_candidates": 8,
        "max_list_items": 10,
        "max_text_chars": 1600,
        "failure_mode": "deterministic_fallback_with_visible_warning",
    }
    llm_agents = manifest["llm"]["agents"]
    assert {
        agent_id
        for agent_id, spec in llm_agents.items()
        if spec.get("enabled", True)
    } == {
        "purchase_intake_analyst",
        "purchase_total_cost_analyst",
        "purchase_risk_reviewer",
        "purchase_recommendation_auditor",
        "purchase_report_writer",
    }
    assert llm_agents["purchase_market_researcher"]["enabled"] is False
    assert llm_agents["purchase_knowledge_retriever"]["enabled"] is False


def test_purchasing_manager_sample_market_observations_are_source_backed():
    sample_root = ROOT / "purchasing_manager" / "examples" / "sample_inputs"
    observations = json.loads((sample_root / "observed_ai_systems.json").read_text())
    combined = "\n".join(
        path.read_text()
        for path in sample_root.iterdir()
        if path.is_file() and path.suffix in {".json", ".md", ".txt"}
    ).lower()

    assert observations["schema"] == "mn.sample.public_market_observations.v1"
    assert len(observations["economic_sources"]) == 2
    assert len(observations["candidates"]) == 3
    assert all(item["source_url"].startswith("https://") for item in observations["candidates"])
    assert all(item["observed_at"] == "2026-08-28" for item in observations["candidates"])
    assert all(item["source_type"] != "fictional_quote" for item in observations["candidates"])
    assert "fictional supplier" not in combined
    assert "sample_ai_workstation_quotes" not in combined


def test_purchasing_manager_merged_config_stages_the_bundled_plain_text_request():
    blueprint = ROOT / "purchasing_manager"
    config = load_blueprint_config(blueprint)
    assert config is not None
    assert config["inputs"]["payload"]["input_folder"] == "@/examples/sample_inputs"

    payloads: dict[str, bytes] = {}
    summary = stage_local_input_payloads(config, payloads, bundle_dir=blueprint)

    assert summary["folders"][0]["config_path"] == "inputs.payload.input_folder"
    assert config["inputs"]["payload"]["input_folder"] == "mn_local_inputs/purchasing_manager_documents"
    assert config["state"]["input_folder"] == "mn_local_inputs/purchasing_manager_documents"
    assert (
        "runtime/mn_local_inputs/purchasing_manager_documents/purchase_request.txt"
        in payloads
    )


def test_purchasing_manager_uses_unified_browser_for_supplied_links_before_queries():
    result = run_payload_script(
        "purchasing_manager",
        """
import json
from domain import research

class BrowserConfig:
    def __init__(self, **values):
        self.values = values

calls = []

def browse(url, config=None, depth=None, output_format=None):
    calls.append({"operation": "browse", "depth": depth, "output_format": output_format})
    return {"status": "ok", "final_url": url, "title": "Seed lead", "text": "Public listing search page"}

def research_topic(query, config=None, depth=None, max_sources=None, output_format=None):
    calls.append({"operation": "research_topic", "depth": depth, "output_format": output_format})
    return []

research._load_web_browser_skill = lambda: (BrowserConfig, browse, research_topic)
sources, warnings = research.research_public_sources(
    ["local AI workstation suppliers"],
    {"internet_research": {"enabled": True, "rendered_browser": {"enabled": False}}},
    seed_urls=["https://example.com/public-lead"],
)
print(json.dumps({
    "urls": [item["url"] for item in sources],
    "queries": [item["query"] for item in sources],
    "calls": calls,
    "warnings": warnings,
}))
""",
    )
    assert result == {
        "urls": ["https://example.com/public-lead"],
        "queries": ["User-supplied public research lead"],
        "calls": [
            {
                "operation": "browse",
                "depth": "standard",
                "output_format": "plain_text",
            },
            {
                "operation": "research_topic",
                "depth": "standard",
                "output_format": "plain_text",
            },
        ],
        "warnings": [],
    }


def test_purchasing_manager_public_queries_are_concise_and_procurement_specific():
    result = run_payload_script(
        "purchasing_manager",
        """
import json
from domain.research import build_public_queries

queries = build_public_queries({
    "purchase_type": "computer",
    "item_description": "Source one supportable local-AI desktop for a Boston engineering office. Two engineers need it for private model prototyping and smaller fine-tuning jobs.",
    "budget": 5000,
    "location": "Boston, MA",
    "priorities": ["technical fit", "risk-adjusted three-year total cost"],
    "constraints": {
        "min_gpu_vram_gb": 16,
        "min_system_ram_gb": 64,
        "min_storage_tb": 2,
        "min_warranty_years": 1,
    },
})
print(json.dumps({"queries": queries, "lengths": [len(query) for query in queries]}))
""",
    )
    assert result["queries"] == [
        "local AI desktop workstation Boston, MA current price in stock comparable alternatives under $5,000",
        "local AI desktop workstation official specifications GPU memory CPU RAM storage power requirements 16GB GPU VRAM 64GB RAM 2TB storage 1 year warranty",
        "local AI desktop workstation three year total cost electricity reliability repair downtime support resale value 16GB GPU VRAM 64GB RAM 2TB storage 1 year warranty",
    ]
    assert max(result["lengths"]) <= 240


def test_purchasing_manager_skips_generic_search_when_seed_sources_are_sufficient():
    result = run_payload_script(
        "purchasing_manager",
        """
import json
from domain import research

class BrowserConfig:
    def __init__(self, **values):
        self.values = values

calls = []

def browse(url, **_):
    calls.append(["browse", url])
    return {"status": "ok", "final_url": url, "title": url, "text": "Current public supplier observation"}

def research_topic(query, **_):
    calls.append(["research_topic", query])
    return []

research._load_web_browser_skill = lambda: (BrowserConfig, browse, research_topic)
sources, warnings = research.research_public_sources(
    ["fallback query"],
    {"internet_research": {
        "enabled": True,
        "max_seed_urls": 4,
        "min_observed_sources_before_search": 3,
        "search_only_when_source_gap": True,
    }},
    seed_urls=[f"https://supplier{i}.example/product" for i in range(4)],
)
print(json.dumps({"calls": calls, "source_count": len(sources), "warnings": warnings}))
""",
    )
    assert result["source_count"] == 4
    assert result["warnings"] == []
    assert [call[0] for call in result["calls"]] == ["browse"] * 4


def test_purchasing_manager_plain_text_request_overrides_fallbacks_and_rejects_private_links():
    result = run_payload_script(
        "purchasing_manager",
        """
import json
from domain.inputs import resolve_request_from_documents

inputs, request = resolve_request_from_documents(
    {
        "purchase_type": "custom",
        "item_description": "Read the purchase request from the input folder.",
    },
    [{
        "name": "my_notes.txt",
        "suffix": ".txt",
        "source_ref": "local:my_notes.txt",
        "text": '''
What I want to buy: A reliable used hybrid SUV.
Budget: $30,000
Research:
- https://example.com/cars?zip=02110#offers
- http://127.0.0.1/private
- https://example.com/private?token=secret
''',
    }],
)
print(json.dumps({
    "purchase_type": inputs["purchase_type"],
    "item_description": inputs["item_description"],
    "budget": inputs["budget"],
    "source_ref": request["source_ref"],
    "research_links": request["research_links"],
}))
""",
    )
    assert result == {
        "purchase_type": "car",
        "item_description": "A reliable used hybrid SUV.",
        "budget": 30000.0,
        "source_ref": "local:my_notes.txt",
        "research_links": ["https://example.com/cars?zip=02110"],
    }


def test_purchasing_manager_uses_five_bounded_llm_narrative_calls_without_changing_economics(tmp_path):
    result = run_payload_script(
        "purchasing_manager",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

class BusinessNarrativeLLM:
    provider = "fake"
    model = "business-narrative"
    fallback_calls = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    estimated_tokens = 0

    def __init__(self):
        self.calls = 0
        self.prompts = []

    def generate_json(self, *, system_prompt, user_prompt, fallback):
        self.calls += 1
        self.prompts.append({{"system": system_prompt, "user": user_prompt}})
        response = {{key: value for key, value in fallback.items() if not key.startswith("_")}}
        if "primary_cost_drivers" in fallback:
            response["summary"] = "Lifecycle exposure is driven by acquisition, operating, and disruption assumptions; the deterministic table remains authoritative."
        elif "overall_posture" in fallback:
            response["overall_posture"] = "moderate"
            response["negotiation_points"] = ["Require a written configuration and support commitment before approval."]
        elif "why_preferred" in fallback:
            response["why_preferred"] = "The preferred option is the highest-ranked eligible candidate in the deterministic comparison."
            response["strongest_reason_to_proceed"] = "The preferred option passes the declared hard gates."
        elif "executive_summary" in fallback:
            response["executive_summary"] = "The preferred option merits conditional approval after source refresh, written quote, and technical sign-off."
            response["decision_rationale"] = "Deterministic eligibility and lifecycle ranking support the decision while unresolved commercial evidence limits commitment."
        return response

root = Path({str((ROOT / 'purchasing_manager').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
llm = BusinessNarrativeLLM()
run = run_blueprint(
    inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out)}},
    config={{"execution": {{"quick_test": True}}}},
    llm_client=llm,
    runs_root=out / "runs",
    run_id="purchase-llm-narrative",
)
artifact = run["final_artifact"]
report = (out / "purchasing_manager_report.md").read_text()
print(json.dumps({{
    "run_status": run["status"],
    "calls": llm.calls,
    "generation": artifact["llm_generation"],
    "usage": artifact["llm_usage"],
    "action": artifact["recommended_action"],
    "preferred": artifact["preferred_candidate"],
    "landed": artifact["candidate_comparisons"][0]["tco"]["landed_acquisition_cost"],
    "risk_npv": artifact["candidate_comparisons"][0]["tco"]["risk_adjusted_npv_tco"],
    "analysis_summary": artifact["analysis_interpretation"]["summary"],
    "risk_posture": artifact["risk_interpretation"]["overall_posture"],
    "decision_reason": artifact["decision_analysis"]["why_preferred"],
    "report_summary": artifact["report_narrative"]["executive_summary"],
    "max_prompt_chars": max(len(item["user"]) for item in llm.prompts),
    "intake_excludes_document_text": '\"text\":' not in llm.prompts[0]["user"] and '\"text_included\": false' in llm.prompts[0]["user"],
    "report_has_financial_interpretation": "## Financial Interpretation" in report,
    "report_has_risk_interpretation": "## Risk Interpretation" in report,
    "executive_heading_count": report.count("## Executive Summary"),
}}))
""",
    )
    assert result["run_status"] == "completed"
    assert result["calls"] == 5
    assert result["generation"]["calls_made"] == 5
    assert result["generation"]["status"] == "completed"
    assert set(result["generation"]["phases"]) == {
        "purchase_intake_analyst",
        "purchase_total_cost_analyst",
        "purchase_risk_reviewer",
        "purchase_recommendation_auditor",
        "purchase_report_writer",
    }
    assert result["usage"]["calls"] == 5
    assert result["action"] == "consider"
    assert result["preferred"] == "microcenter-powerspec-g913"
    assert result["landed"] == 4501.23
    assert result["risk_npv"] == 7956.96
    assert result["analysis_summary"].startswith("Lifecycle exposure")
    assert result["risk_posture"] == "moderate"
    assert result["decision_reason"].startswith("The preferred option")
    assert result["report_summary"].startswith("The preferred option merits")
    assert result["max_prompt_chars"] <= 30000
    assert result["intake_excludes_document_text"] is True
    assert result["report_has_financial_interpretation"] is True
    assert result["report_has_risk_interpretation"] is True
    assert result["executive_heading_count"] == 1


def test_purchasing_manager_rejects_invented_numbers_and_unknown_references(tmp_path):
    result = run_payload_script(
        "purchasing_manager",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

class HallucinatingLLM:
    provider = "fake"
    model = "hallucinating"
    fallback_calls = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    estimated_tokens = 0

    def __init__(self):
        self.calls = 0

    def generate_json(self, *, system_prompt, user_prompt, fallback):
        self.calls += 1
        response = {{key: value for key, value in fallback.items() if not key.startswith("_")}}
        if "primary_cost_drivers" in fallback:
            response["summary"] = "The hidden cost is $999999."
            response["primary_cost_drivers"] = [{{"candidate_id": "invented-candidate", "metric_refs": ["invented.metric"], "explanation": "Unsupported."}}]
            response["source_refs"] = ["https://invented.example/source"]
        elif "overall_posture" in fallback:
            response["material_risks"] = [{{"candidate_id": "invented-candidate", "severity": "critical", "reason": "Unsupported $999999 exposure.", "mitigation": "None", "owner_role": "Nobody", "blocks_commitment": False, "evidence_refs": ["invented"]}}]
        elif "why_preferred" in fallback:
            response["why_not_alternatives"] = [{{"candidate_id": "invented-candidate", "explanation": "Unsupported."}}]
        elif "executive_summary" in fallback:
            response["executive_summary"] = "Approve an invented $999999 budget."
        return response

root = Path({str((ROOT / 'purchasing_manager').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
llm = HallucinatingLLM()
run = run_blueprint(
    inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out)}},
    config={{"execution": {{"quick_test": True}}}},
    llm_client=llm,
    runs_root=out / "runs",
    run_id="purchase-invalid-llm",
)
artifact = run["final_artifact"]
serialized = json.dumps(artifact)
print(json.dumps({{
    "run_status": run["status"],
    "calls": llm.calls,
    "generation_status": artifact["llm_generation"]["status"],
    "fallback_calls": artifact["llm_usage"]["fallback_calls"],
    "warning_count": len([item for item in artifact["warnings"] if item.get("kind") == "llm_analysis"]),
    "action": artifact["recommended_action"],
    "preferred": artifact["preferred_candidate"],
    "landed": artifact["candidate_comparisons"][0]["tco"]["landed_acquisition_cost"],
    "risk_npv": artifact["candidate_comparisons"][0]["tco"]["risk_adjusted_npv_tco"],
    "contains_invented_number": "999999" in serialized,
    "contains_invented_candidate": "invented-candidate" in serialized,
    "contains_invented_source": "invented.example" in serialized,
}}))
""",
    )
    assert result == {
        "run_status": "completed_with_fallback",
        "calls": 5,
        "generation_status": "completed_with_fallback",
        "fallback_calls": 4,
        "warning_count": 4,
        "action": "consider",
        "preferred": "microcenter-powerspec-g913",
        "landed": 4501.23,
        "risk_npv": 7956.96,
        "contains_invented_number": False,
        "contains_invented_candidate": False,
        "contains_invented_source": False,
    }


def test_purchasing_manager_model_failure_completes_with_visible_deterministic_fallback(tmp_path):
    result = run_payload_script(
        "purchasing_manager",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

class FailingLLM:
    provider = "fake"
    model = "unavailable"
    fallback_calls = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    estimated_tokens = 0

    def __init__(self):
        self.calls = 0

    def generate_json(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return ["malformed structured output"]
        raise TimeoutError("model endpoint timed out")

root = Path({str((ROOT / 'purchasing_manager').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
llm = FailingLLM()
run = run_blueprint(
    inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out)}},
    config={{"execution": {{"quick_test": True}}}},
    llm_client=llm,
    runs_root=out / "runs",
    run_id="purchase-llm-failure",
)
artifact = run["final_artifact"]
report = (out / "purchasing_manager_report.md").read_text()
print(json.dumps({{
    "run_status": run["status"],
    "calls": llm.calls,
    "generation_status": artifact["llm_generation"]["status"],
    "phase_count": len(artifact["llm_generation"]["phases"]),
    "warning_count": len([item for item in artifact["warnings"] if item.get("kind") == "llm_analysis"]),
    "action": artifact["recommended_action"],
    "preferred": artifact["preferred_candidate"],
    "report_exists": (out / "purchasing_manager_report.md").exists(),
    "visible_warning": "LLM fallback warning" in report,
}}))
""",
    )
    assert result == {
        "run_status": "completed_with_fallback",
        "calls": 5,
        "generation_status": "completed_with_fallback",
        "phase_count": 5,
        "warning_count": 5,
        "action": "consider",
        "preferred": "microcenter-powerspec-g913",
        "report_exists": True,
        "visible_warning": True,
    }
