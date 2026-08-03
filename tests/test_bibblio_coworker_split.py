from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
for source in sorted((WORKSPACE / "mn-skills").glob("*/src")):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

BLUEPRINTS = {
    "bibblio_gtm_coworker": ("bibblio_growth_lead", ["qualify_seed_contacts", "publish_gtm_outreach_queue"]),
    "bibblio_finance_coworker": ("bibblio_finance_controller", ["calculate_unit_economics", "publish_financial_control_packet"]),
    "bibblio_learning_safety_coworker": ("bibblio_learning_safety_director", ["review_learning_backlog", "publish_learning_safety_packet"]),
    "bibblio_content_studio_coworker": ("bibblio_content_studio_director", ["plan_content_batch", "publish_content_studio_packet"]),
    "bibblio_parent_lifecycle_coworker": ("bibblio_parent_lifecycle_director", ["diagnose_parent_journey", "publish_parent_lifecycle_packet"]),
}


def test_five_independent_blueprints_share_one_goal_contract():
    for blueprint_id, (agent_id, step_ids) in BLUEPRINTS.items():
        manifest = json.loads((ROOT / blueprint_id / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["identity"]["id"] == blueprint_id
        assert manifest["metadata"]["business_goal"] == "Turn Bibblio into a profitable business."
        assert manifest["metadata"]["collaboration_group"] == "bibblio-profitability-team"
        assert list(manifest["agents"]["registry"]) == [agent_id]
        assert [step["id"] for step in manifest["workflow"]["steps"]] == step_ids
        assert manifest["workflow"]["steps"][1]["needs"] == [step_ids[0]]
        assert "mirrorneuron-goal-work-packet-skill" in {
            dependency["name"] for dependency in manifest["skill_dependencies"]
        }
        assert "mirrorneuron-mcp-server-skill" in {
            dependency["name"] for dependency in manifest["skill_dependencies"]
        }
        assert "mirrorneuron-mcp-client-skill" in {
            dependency["name"] for dependency in manifest["skill_dependencies"]
        }
        assert manifest["mcp_collaboration"]["enabled"] is True
        config = json.loads(
            (ROOT / blueprint_id / "config" / "default.json").read_text(
                encoding="utf-8"
            )
        )
        assert config["mcp_collaboration"]["chat_grace_seconds"] == 8
        assert manifest["agents"]["auxiliary_entrypoints"] == [
            "mcp_collaboration_server"
        ]
        service_node = next(
            node
            for node in manifest["agents"]["extra_nodes"]
            if node["node_id"] == "mcp_collaboration_server"
        )
        assert service_node["config"]["command"] == ["mn-job-mcp-server"]
        assert service_node["config"]["environment"]["MN_BLUEPRINT_ID"] == blueprint_id
        assert service_node["config"]["pass_env"] == [
            "MN_MCP_CONTAINER_LOOPBACK_PROXY"
        ]
        assert service_node["resources"]["ports"] == [
            {
                "label": "mcp-collaboration",
                "port": "auto",
                "protocol": "http",
            }
        ]
        assert service_node["services"][0]["name"] == "mn-job-collaboration"
        assert service_node["services"][0]["port"] == "${env.MN_PORT_MCP_COLLABORATION}"
        assert set(service_node["services"][0]["tags"]) == {
            "mcp",
            "job-collaboration",
        }
        assert service_node["services"][0]["meta"]["job_id"] == "${env.MN_JOB_ID}"
        assert service_node["services"][0]["meta"]["run_id"] == "${env.MN_RUN_ID}"
        assert service_node["services"][0]["checks"][0]["interval_ms"] == 100
        assert (ROOT / blueprint_id / "payloads" / "prompts").is_dir()


def test_catalog_replaces_the_monolith_with_five_collaboration_group_members():
    entries = {entry["id"]: entry for entry in json.loads((ROOT / "index.json").read_text(encoding="utf-8"))}
    assert "bibblio_profitability_workforce" not in entries
    assert set(BLUEPRINTS) <= set(entries)
    for blueprint_id in BLUEPRINTS:
        product = entries[blueprint_id]["product"]
        assert product["business_goal"] == "Turn Bibblio into a profitable business."
        assert product["collaboration_group"] == "bibblio-profitability-team"
        assert entries[blueprint_id]["mcp_collaboration"] == {
            "enabled": True,
            "goal_id": "bibblio-profitable-business",
            "path": "/mcp",
            "service_name": "mn-job-collaboration",
            "service_tags": ["mcp", "job-collaboration"],
            "transport": "streamable-http",
        }


def test_gtm_fixture_is_synthetic_and_mcp_packet_excludes_contact_fields():
    sample_path = ROOT / "bibblio_gtm_coworker" / "examples" / "sample_inputs" / "edtech_contacts_sample.csv"
    with sample_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["Email"].endswith("@example.invalid") for row in rows)

    source = (ROOT / "bibblio_gtm_coworker" / "payloads" / "domain" / "workers.py").read_text(encoding="utf-8")
    assert '"send_authorized": False' in source
    assert '"private_fields_excluded_from_mcp": ["name", "email", "note", "individual draft body"]' in source


def test_finance_fixture_retains_deterministic_economics():
    payloads = ROOT / "bibblio_finance_coworker" / "payloads"
    if str(payloads) not in sys.path:
        sys.path.insert(0, str(payloads))
    module = importlib.import_module("domain.metrics")
    fixture = json.loads(
        (ROOT / "bibblio_finance_coworker" / "examples" / "sample_inputs" / "business_metrics.json").read_text()
    )
    values = module.calculate_unit_economics(fixture)["metrics"]
    assert values["monthly_revenue"] == 1409.06
    assert values["monthly_contribution_after_fixed_costs_and_acquisition"] == -5300.9332
    assert values["break_even_paying_families"] == 548


def test_role_specific_safety_fixtures_are_present():
    learning = json.loads(
        (ROOT / "bibblio_learning_safety_coworker" / "examples" / "sample_inputs" / "content_backlog.json").read_text()
    )
    assert any(item["claim_risk"] == "blocked" for item in learning["items"])

    content = json.loads(
        (ROOT / "bibblio_content_studio_coworker" / "examples" / "sample_inputs" / "approved_learning_briefs.json").read_text()
    )
    statuses = {item["learning_review_status"] for item in content["briefs"]}
    assert {"PASS", "PASS WITH CONDITIONS", "REVISE"} <= statuses

    with (ROOT / "bibblio_parent_lifecycle_coworker" / "examples" / "sample_inputs" / "parent_feedback.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        feedback = list(csv.DictReader(handle))
    assert feedback and all(row["data_status"] == "synthetic_demo" for row in feedback)
