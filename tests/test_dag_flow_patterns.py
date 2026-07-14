from __future__ import annotations

import json
from pathlib import Path

from mn_sdk.manifest_converter import expand_manifest_source, is_manifest_source
from mn_sdk.submission_preparation import lower_manifest_topology_for_runtime_submission


ROOT = Path(__file__).resolve().parents[1]


def _runtime_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if is_manifest_source(manifest):
        manifest = expand_manifest_source(manifest, root_dir=path.parent)
    lower_manifest_topology_for_runtime_submission(manifest)
    return manifest


def _is_acyclic(step_ids: set[str], edges: list[dict]) -> bool:
    parents = {step_id: set() for step_id in step_ids}
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        if source in parents and target in parents:
            parents[target].add(source)

    resolved: set[str] = set()
    while ready := {step_id for step_id, dependencies in parents.items() if step_id not in resolved and dependencies <= resolved}:
        resolved.update(ready)
    return resolved == step_ids


def test_every_catalog_blueprint_lowers_its_declared_workflow_into_the_core_dag():
    manifest_paths = sorted(ROOT.glob("*/manifest.json"))
    assert manifest_paths

    for path in manifest_paths:
        manifest = _runtime_manifest(path)
        flow = manifest["flow"]
        steps = flow["steps"]
        graph_edges = flow["graph"]["edges"]
        node_ids = {node["node_id"] for node in flow["nodes"]}
        step_ids = {step["id"] for step in steps}

        assert steps, path.parent.name
        assert graph_edges or len(steps) == 1, path.parent.name
        assert _is_acyclic(step_ids, graph_edges), path.parent.name
        assert all(step["trigger_rule"] == "all_success" or step["id"] in {"advisor_evidence_reconciler", "legal_evidence_reconciler"} for step in steps), path.parent.name
        assert all((step.get("agent_id") or step["run"]) in node_ids for step in steps), path.parent.name


def test_financial_legal_and_vc_blueprints_compile_to_fork_join_dags():
    for blueprint_id, join_step in (
        ("financial_advisor", "advisor_evidence_reconciler"),
        ("legal_assistant", "legal_evidence_reconciler"),
        ("vc_assistant", "score_consistency_auditor"),
    ):
        manifest = _runtime_manifest(ROOT / blueprint_id / "manifest.json")
        edges = manifest["flow"]["graph"]["edges"]
        parents = [edge["from"] for edge in edges if edge["to"] == join_step]
        fan_out_sources = {edge["from"] for edge in edges}

        assert len(parents) > 1, blueprint_id
        assert any(sum(edge["from"] == source for edge in edges) > 1 for source in fan_out_sources), blueprint_id


def test_vc_scorers_share_a_single_predecessor_and_do_not_depend_on_each_other():
    manifest = _runtime_manifest(ROOT / "vc_assistant" / "manifest.json")
    edges = manifest["flow"]["graph"]["edges"]
    scorer_ids = {
        "berkus_scorer",
        "scorecard_bill_payne_scorer",
        "risk_factor_summation_scorer",
        "venture_capital_method_scorer",
        "first_chicago_scorer",
        "comparables_market_multiple_scorer",
        "cost_to_duplicate_scorer",
    }

    scorer_edges = [edge for edge in edges if edge["to"] in scorer_ids]
    assert {(edge["from"], edge["to"]) for edge in scorer_edges} == {
        ("research_reconciler", scorer_id) for scorer_id in scorer_ids
    }
