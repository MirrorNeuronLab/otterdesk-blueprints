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
    while ready := {
        step_id
        for step_id, dependencies in parents.items()
        if step_id not in resolved and dependencies <= resolved
    }:
        resolved.update(ready)
    return resolved == step_ids


def test_every_catalog_blueprint_lowers_its_declared_workflow_into_the_core_dag():
    manifest_paths = [
        path
        for path in sorted(ROOT.glob("*/manifest.json"))
        if (json.loads(path.read_text(encoding="utf-8")).get("standard") or {}).get(
            "profile"
        )
        == "blueprint"
    ]
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
        assert all(
            step["trigger_rule"] == "all_success"
            or step["id"]
            in {"advisor_evidence_reconciler", "legal_evidence_reconciler"}
            for step in steps
        ), path.parent.name
        assert all(
            (step.get("agent_id") or step["run"]) in node_ids for step in steps
        ), path.parent.name


def test_migrated_vc_blueprint_compiles_to_redis_routed_fork_join_crews():
    manifest = _runtime_manifest(ROOT / "vc_assistant" / "manifest.json")
    edges = manifest["agents"]["edges"]

    for coordinator, expected_count in (
        ("collect_public_research", 5),
        ("calculate_valuation_scores", 7),
    ):
        outbound = [
            edge
            for edge in edges
            if edge["from_node"] == coordinator and "__" in edge["to_node"]
        ]
        inbound = [
            edge
            for edge in edges
            if edge["to_node"] == coordinator and "__" in edge["from_node"]
        ]
        assert len(outbound) == expected_count
        assert len(inbound) == expected_count


def test_vc_scorers_share_a_single_predecessor_and_do_not_depend_on_each_other():
    manifest = _runtime_manifest(ROOT / "vc_assistant" / "manifest.json")
    edges = manifest["agents"]["edges"]
    scorer_ids = {
        "berkus_scorer",
        "scorecard_bill_payne_scorer",
        "risk_factor_summation_scorer",
        "venture_capital_method_scorer",
        "first_chicago_scorer",
        "comparables_market_multiple_scorer",
        "cost_to_duplicate_scorer",
    }

    invocation_ids = {
        f"calculate_valuation_scores__{scorer_id}" for scorer_id in scorer_ids
    }
    scorer_edges = [edge for edge in edges if edge["to_node"] in invocation_ids]
    assert {(edge["from_node"], edge["to_node"]) for edge in scorer_edges} == {
        ("calculate_valuation_scores", invocation_id)
        for invocation_id in invocation_ids
    }
    assert not any(
        edge["from_node"] in invocation_ids and edge["to_node"] in invocation_ids
        for edge in edges
    )


def test_default_llm_blueprints_keep_litellm_routing_logical():
    for blueprint_id in (
        "vc_assistant",
        "legal_assistant",
        "financial_advisor",
        "purchase_research_assistant",
    ):
        config = json.loads(
            (ROOT / blueprint_id / "config" / "default.json").read_text(
                encoding="utf-8"
            )
        )
        assert config["llm"]["model"] == "default", blueprint_id


def test_purchase_research_workers_use_the_logical_default_model():
    blueprint = ROOT / "purchase_research_assistant"
    manifest = json.loads((blueprint / "manifest.json").read_text(encoding="utf-8"))
    payload_config = json.loads(
        (blueprint / "payloads" / "config" / "default.json").read_text(encoding="utf-8")
    )

    workers = [
        worker
        for binding in manifest["runtime"]["bindings"].values()
        for worker in binding.get("workers", [])
    ]
    assert workers
    assert {worker["model"] for worker in workers} == {"default"}
    assert manifest["runtime"]["worker_defaults"]["model"] == "default"
    assert payload_config["llm"]["model"] == "default"
    assert "runtime_model" not in payload_config["llm"]
