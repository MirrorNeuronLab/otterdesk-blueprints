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
    "prepare_legal_matter",
    "analyze_legal_documents",
    "reconcile_legal_review",
    "publish_legal_review_packet",
]


def test_legal_manifest_compiles_parallel_invoice_and_contract_lanes():
    source = source_manifest("legal_assistant")
    expanded = expanded_manifest("legal_assistant")
    assert [step["id"] for step in source["workflow"]["steps"]] == EXPECTED_STEPS
    edges = expanded["agents"]["edges"]
    assert any(edge["from_node"] == "analyze_legal_documents__fork_1" and edge["to_node"] == "analyze_legal_documents__invoice_extract" for edge in edges)
    assert any(edge["from_node"] == "analyze_legal_documents__fork_1" and edge["to_node"] == "analyze_legal_documents__clause_extract" for edge in edges)
    assert any(edge["to_node"] == "analyze_legal_documents__join_2" for edge in edges)


def test_legal_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("legal_assistant")
    assert_registry_handlers_import("legal_assistant")


def test_legal_compiled_docker_workers_ship_the_domain_llm_handlers():
    expanded = expanded_manifest("legal_assistant")
    worker_nodes = [
        node
        for node in expanded["agents"]["nodes"]
        if (node.get("config") or {}).get("runner_module")
        == "MirrorNeuron.Runner.DockerWorker"
    ]

    assert worker_nodes
    assert all(
        {"source": "domain", "target": "domain"}
        in node["config"]["upload_paths"]
        for node in worker_nodes
    )


def test_legal_audit_invokes_each_configured_llm_reviewer(tmp_path):
    result = run_payload_script(
        "legal_assistant",
        f"""
import json
from pathlib import Path

from domain.contracts import compare_contracts, extract_contracts
from domain.documents import read_documents, watch
from domain.invoices import extract_invoices, validate_payables
from domain.review import audit_review, reconcile_evidence
from domain.runtime_services import runtime_context_for_step
from domain.state import load_state


class RecordingLLM:
    provider = "docker_model_runner"
    model = "gemma4:e2b"
    fallback_calls = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    estimated_tokens = 0
    runtime_selection = {{"selected_model": "small"}}

    def __init__(self):
        self.calls = 0

    def generate_json(self, *, system_prompt, user_prompt, fallback):
        self.calls += 1
        return dict(fallback)


root = Path({str((ROOT / 'legal_assistant').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
context = runtime_context_for_step(
    inputs={{
        "document_folder": str(root / "examples" / "sample_inputs"),
        "output_folder": str(out),
    }},
    config={{
        "execution": {{"quick_test": True}},
        "knowledge_rag": {{"enabled": False}},
    }},
    runs_root=str(out / "runs"),
    run_id="legal-llm-contract",
)
llm = RecordingLLM()
context["llm_client"] = llm
for operation in (
    watch,
    read_documents,
    extract_invoices,
    validate_payables,
    extract_contracts,
    compare_contracts,
    reconcile_evidence,
    audit_review,
):
    operation(context)
state = load_state(context)
print(json.dumps({{
    "calls": llm.calls,
    "actors": sorted(state["actor_findings"]),
    "provider": state["llm_usage"]["provider"],
    "rag_status": state["rag"]["status"],
}}))
""",
    )
    assert result == {
        "calls": 7,
        "actors": [
            "contract_clause_extractor",
            "contract_playbook_comparator",
            "invoice_bill_extractor",
            "legal_evidence_reconciler",
            "legal_reporter",
            "legal_review_auditor",
            "payable_field_validator",
        ],
        "provider": "docker_model_runner",
        "rag_status": "disabled",
    }


def test_legal_sample_prioritizes_payment_control_and_obligations(tmp_path):
    result = run_payload_script(
        "legal_assistant",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

root = Path({str((ROOT / 'legal_assistant').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
run = run_blueprint(
    inputs={{"document_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out), "quick_test": True}},
    config={{"execution": {{"quick_test": True}}}},
    runs_root=out / "runs",
    run_id="legal-quality",
)
artifact = run["final_artifact"]
priority = artifact["priority_review_queue"][0]
state_root = out / "runs" / "legal-quality" / "workflow_state"
print(json.dumps({{
    "status": artifact["status"],
    "matter": artifact["matter_overview"],
    "priority_area": priority["area"],
    "priority_severity": priority["severity"],
    "requires_trusted_verification": "trusted" in priority["required_control"].lower(),
    "obligation_count": len(artifact["obligation_calendar"]),
    "lane_files": sorted(path.name for path in state_root.glob("legal_*_lane.json")),
    "run_artifact_exists": (out / "runs" / "legal-quality" / "final_artifact.json").exists(),
}}))
""",
    )
    assert result["status"] == "review_ready_with_issues"
    assert result["matter"] == {
        "document_count": 6,
        "invoice_count": 2,
        "contract_count": 2,
        "high_severity_issue_count": 1,
        "open_obligation_count": 8,
    }
    assert result["priority_area"] == "payment_controls"
    assert result["priority_severity"] == "high"
    assert result["requires_trusted_verification"] is True
    assert result["obligation_count"] == 8
    assert result["lane_files"] == ["legal_contract_lane.json", "legal_invoice_lane.json"]
    assert result["run_artifact_exists"] is True
