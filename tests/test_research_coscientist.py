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
    "frame_research_problem",
    "build_research_evidence",
    "develop_and_challenge_hypotheses",
    "verify_and_publish_research_packet",
]


def test_research_manifest_has_one_isolated_autonomous_specialist():
    source = source_manifest("research_coscientist")
    expanded = expanded_manifest("research_coscientist")
    assert [step["id"] for step in source["workflow"]["steps"]] == EXPECTED_STEPS
    openshell = [
        node
        for node in expanded["agents"]["nodes"]
        if (node.get("config") or {}).get("runner_module") == "MirrorNeuron.Runner.OpenShell"
    ]
    assert [node["node_id"] for node in openshell] == [
        "develop_and_challenge_hypotheses__autonomous_researcher"
    ]
    assert openshell[0]["config"]["reuse_shared_sandbox"] is True


def test_research_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("research_coscientist")
    assert_registry_handlers_import("research_coscientist")


def test_research_sample_audits_falsifiable_hypotheses(tmp_path):
    result = run_payload_script(
        "research_coscientist",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

root = Path({str((ROOT / 'research_coscientist').resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
run = run_blueprint(
    inputs={{"input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out)}},
    config={{"execution": {{"quick_test": True}}}},
    runs_root=out / "runs",
    run_id="research-quality",
)
artifact = run["final_artifact"]
hypothesis = artifact["hypothesis_ledger"][0]
print(json.dumps({{
    "run_status": run["status"],
    "packet_status": artifact["status"],
    "audit_status": artifact["packet_audit"]["status"],
    "all_checks_pass": all(item["passed"] for item in artifact["packet_audit"]["checks"]),
    "has_prediction": bool(hypothesis["prediction"]),
    "has_counterargument": bool(hypothesis["counterargument"]),
    "has_disconfirmation": bool(hypothesis["disconfirming_observation"]),
    "sample_hypothesis_is_specific": "pump-speed" in hypothesis["statement"] and "3%" in hypothesis["prediction"],
    "baseline_is_evidence": "local:sample_baseline_measurements.csv" in hypothesis["evidence_support"],
    "rag_status": artifact["knowledge_rag"]["status"],
    "trace_count": len(artifact["autonomous_research"]["session"]["trace"]),
    "run_artifact_exists": (out / "runs" / "research-quality" / "final_artifact.json").exists(),
    "brief_exists": (out / "research_brief.md").exists(),
}}))
""",
    )
    assert result == {
        "run_status": "completed",
        "packet_status": "review_ready",
        "audit_status": "passed",
        "all_checks_pass": True,
        "has_prediction": True,
        "has_counterargument": True,
        "has_disconfirmation": True,
        "sample_hypothesis_is_specific": True,
        "baseline_is_evidence": True,
        "rag_status": "skipped_quick_test",
        "trace_count": 3,
        "run_artifact_exists": True,
        "brief_exists": True,
    }
