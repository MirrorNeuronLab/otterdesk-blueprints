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
        "open_obligation_count": 7,
    }
    assert result["priority_area"] == "payment_controls"
    assert result["priority_severity"] == "high"
    assert result["requires_trusted_verification"] is True
    assert result["obligation_count"] == 7
    assert result["lane_files"] == ["legal_contract_lane.json", "legal_invoice_lane.json"]
    assert result["run_artifact_exists"] is True
