from __future__ import annotations

import json

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
    "publish_purchase_decision_packet",
]


def test_purchase_manifest_compiles_logical_steps_and_specialist_graphs():
    source = source_manifest("purchase_research_assistant")
    expanded = expanded_manifest("purchase_research_assistant")
    assert source["apiVersion"] == "mn.workflow.source/v2"
    assert [step["id"] for step in source["workflow"]["steps"]] == EXPECTED_STEPS
    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "compare_purchase_options__market" in node_ids
    assert "compare_purchase_options__cost" in node_ids
    assert "compare_purchase_options__risk" in node_ids
    assert "compare_purchase_options__audit" in node_ids
    assert "publish_purchase_decision_packet__end" in node_ids


def test_purchase_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("purchase_research_assistant")
    assert_registry_handlers_import("purchase_research_assistant")


def test_purchase_sample_produces_a_real_candidate_comparison(tmp_path):
    result = run_payload_script(
        "purchase_research_assistant",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

root = Path({str((ROOT / 'purchase_research_assistant').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
run = run_blueprint(
    inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out)}},
    config={{"execution": {{"quick_test": True}}}},
    runs_root=out / "runs",
    run_id="purchase-quality",
)
artifact = run["final_artifact"]
comparisons = artifact["candidate_comparisons"]
print(json.dumps({{
    "status": run["status"],
    "action": artifact["recommended_action"],
    "preferred": artifact["preferred_candidate"],
    "candidate_count": len(comparisons),
    "matching_count": sum(1 for item in comparisons if item["hard_constraints_passed"]),
    "preferred_five_year_cost": comparisons[0]["known_five_year_cost_before_financing_utilities_and_resale"],
    "outside_zip_rejected": comparisons[-1]["hard_constraint_checks"]["zip_code"] is False,
    "gap_count": len(artifact["evidence_gaps"]),
    "rag_status": artifact["knowledge_rag"]["status"],
    "run_artifact_exists": (out / "runs" / "purchase-quality" / "final_artifact.json").exists(),
    "report_exists": (out / "purchase_research_report.md").exists(),
}}))
""",
    )
    assert result == {
        "status": "completed",
        "action": "consider",
        "preferred": "hanover-maple-12",
        "candidate_count": 3,
        "matching_count": 2,
        "preferred_five_year_cost": 781000.0,
        "outside_zip_rejected": True,
        "gap_count": 4,
        "rag_status": "skipped_quick_test",
        "run_artifact_exists": True,
        "report_exists": True,
    }


def test_purchase_config_uses_bundle_paths_and_manifest_owned_descriptors():
    config = json.loads((ROOT / "purchase_research_assistant" / "config" / "default.json").read_text())
    assert config["inputs"]["payload"]["input_folder"] == "@/examples/sample_inputs"
    assert "identity" not in config
    assert "agents" not in config["llm"]
