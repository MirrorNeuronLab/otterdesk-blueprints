from __future__ import annotations

import csv
import hashlib
import importlib
import json
import sys
from pathlib import Path

from workspace_paths import companion_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
for source in sorted((WORKSPACE / "mn-skills").glob("*/src")):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

BLUEPRINTS = {
    "growth_partnerships_coworker": ("growth_partnerships_lead", ["qualify_seed_contacts", "publish_gtm_outreach_queue", "deliver_approved_email"]),
    "business_finance_coworker": ("business_finance_controller", ["calculate_unit_economics", "publish_financial_control_packet"]),
    "learning_quality_safety_coworker": ("learning_quality_safety_director", ["review_learning_backlog", "publish_learning_safety_packet"]),
    "content_studio_coworker": ("content_studio_director", ["plan_content_batch", "publish_content_studio_packet"]),
    "gtm_assistant": (
        ["customer_lifecycle_director", "development_reply_monitor"],
        [
            "diagnose_customer_journey",
            "publish_customer_lifecycle_packet",
            "deliver_approved_lifecycle_email",
            "monitor_development_email_replies",
        ],
    ),
}

PUBLIC_NAMES = {
    "growth_partnerships_coworker": "Growth & Partnerships Co-worker",
    "business_finance_coworker": "Business Finance Co-worker",
    "learning_quality_safety_coworker": "Learning Quality & Safety Co-worker",
    "content_studio_coworker": "Content Studio Co-worker",
    "gtm_assistant": "GTM Assistant",
}

RETIRED_BLUEPRINT_IDS = {
    "bibblio_gtm_coworker",
    "bibblio_finance_coworker",
    "bibblio_learning_safety_coworker",
    "bibblio_content_studio_coworker",
    "bibblio_parent_lifecycle_coworker",
}

UNCHANGED_DEMO_ASSETS = {
    "growth_partnerships_coworker/examples/sample_inputs/SAMPLE_DATASET_MANIFEST.json": "b2d60ab71f3b1eb2169d693ae1406a19071087c8f8a1b022bda6ea53d77403e9",
    "growth_partnerships_coworker/examples/sample_inputs/edtech_contacts_sample.csv": "b9ab0f313aee55650b7d6820b2da0dc8ec2dd332b6b193ec8a06f4f320e175d9",
    "growth_partnerships_coworker/payloads/knowledge/gtm_playbook.md": "d98c562e3156c98a3d901711ad057b3568b31175af6b555c7406f285662413a7",
    "business_finance_coworker/examples/sample_inputs/SAMPLE_DATASET_MANIFEST.json": "c558c53676e7377d724144441e62a7b53fbf1c2249e7434c496e5a6d16be9f5d",
    "business_finance_coworker/examples/sample_inputs/business_metrics.json": "d1a5195b61d4990ed1962e5c3e91ea91e39bf5505bd4e15c9caf1c9cc2b3c457",
    "business_finance_coworker/payloads/knowledge/finance_playbook.md": "8cc280c37a28d8a9539c6d34a83fcceda6b597080e236ed3396d65a4b3be92d9",
    "learning_quality_safety_coworker/examples/sample_inputs/SAMPLE_DATASET_MANIFEST.json": "618aa13d582569dc1aaf7165387ffb69ad9d9dca7e0534a3fcaaaa9460ba9ec3",
    "learning_quality_safety_coworker/examples/sample_inputs/content_backlog.json": "a83700b6dabab09060a7c741ed3f80adca94e721ca003b98da72bdfe7351a36e",
    "learning_quality_safety_coworker/payloads/knowledge/learning_safety_playbook.md": "44281cd687fe42b07693c97e1bda85d15c458b96a916fd2f6b07946f7f82f3b1",
    "content_studio_coworker/examples/sample_inputs/SAMPLE_DATASET_MANIFEST.json": "b03ff1ec1dac1a707fc3fc8cba7c91a14097c1bd828aa5a979b95455cc1b23b5",
    "content_studio_coworker/examples/sample_inputs/approved_learning_briefs.json": "48f86e915f86f81345288f4557473aabc6ee9e031c78b8b55616a8ea767b5afa",
    "content_studio_coworker/payloads/knowledge/content_studio_playbook.md": "bb38345a24ed03a4b3c5a02a83177412a879277d8ba47462564607d18f46a96b",
    "gtm_assistant/examples/sample_inputs/SAMPLE_DATASET_MANIFEST.json": "3bfea624c7279aa87aa9747658c27fffc8e90d75a3d900e56c6042f20e396cfd",
    "gtm_assistant/examples/sample_inputs/parent_feedback.csv": "6e490348b8e4c4b140c559b1c5e4bbdc316af2cc37df667e0ab55dec0f84b5bd",
    "gtm_assistant/payloads/knowledge/parent_lifecycle_playbook.md": "d2506c08e13a2e4218db698aa2aacc0e9fb9606fe7941985c8778ace6cf893a9",
}


def test_five_independent_blueprints_share_one_goal_contract():
    for blueprint_id, (agent_id, step_ids) in BLUEPRINTS.items():
        manifest = json.loads((ROOT / blueprint_id / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["identity"]["id"] == blueprint_id
        assert manifest["identity"]["name"] == PUBLIC_NAMES[blueprint_id]
        assert "Bibblio" not in manifest["identity"]["name"]
        assert manifest["metadata"]["business_goal"] == "Build a successful business for Bibblio."
        assert manifest["metadata"]["collaboration_group"] == "business-success-team"
        expected_agent_ids = [agent_id] if isinstance(agent_id, str) else agent_id
        assert list(manifest["agents"]["registry"]) == expected_agent_ids
        assert [step["id"] for step in manifest["workflow"]["steps"]] == step_ids
        assert manifest["workflow"]["steps"][1]["needs"] == [step_ids[0]]
        if blueprint_id == "growth_partnerships_coworker":
            assert manifest["identity"]["version"] == 1
            assert manifest["identity"]["manifest_version"] == "2.0"
            assert manifest["workflow"]["workflow_id"] == "growth_partnerships_coworker_v2"
            assert manifest["workflow"]["steps"][2]["needs"] == [step_ids[1]]
            assert manifest["workflow"]["steps"][2]["control"]["retry"]["max_attempts"] == 1
            delivery_worker = manifest["workers"]["groups"][0]
            assert delivery_worker["steps"] == ["deliver_approved_email"]
            assert delivery_worker["with"]["side_effect"] == "external"
            assert delivery_worker["with"]["pass_env"] == [
                "MN_SMTP_USERNAME",
                "MN_SMTP_PASSWORD",
                "MN_SMTP_DEV_RECIPIENT",
            ]
            assert "mirrorneuron-email-delivery-skill" in {
                dependency["name"] for dependency in manifest["skill_dependencies"]
            }
        if blueprint_id == "gtm_assistant":
            assert manifest["identity"]["version"] == 1
            assert manifest["workflow"]["workflow_id"] == "gtm_assistant_v4"
            assert manifest["workflow"]["steps"][2]["needs"] == [step_ids[1]]
            assert manifest["workflow"]["steps"][2]["control"]["retry"]["max_attempts"] == 1
            assert manifest["workflow"]["steps"][3]["needs"] == [step_ids[2]]
            assert manifest["type"] == "service"
            assert manifest["service"]["run_until"] == "manual_stop"
            delivery_worker = manifest["workers"]["groups"][0]
            assert delivery_worker["steps"] == [
                "deliver_approved_lifecycle_email",
                "monitor_development_email_replies",
            ]
            assert delivery_worker["with"]["side_effect"] == "external"
            assert delivery_worker["with"]["pass_env"] == [
                "MN_SMTP_USERNAME",
                "MN_SMTP_PASSWORD",
                "MN_SMTP_DEV_RECIPIENT",
            ]
            assert "mirrorneuron-email-delivery-skill" in {
                dependency["name"] for dependency in manifest["skill_dependencies"]
            }
            assert "mn-prototype-supervised-service-agent" in {
                dependency["name"] for dependency in manifest["agent_dependencies"]
            }
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
        assert config["inputs"]["payload"]["business_name"] == "Bibblio"
        assert config["inputs"]["payload"]["planning_horizon_days"] == 90
        required_fields = set(manifest["contracts"]["outputs"]["primary"]["required_fields"])
        assert {
            "role_contribution",
            "north_star_question",
            "role_scorecard",
            "founder_decisions",
            "ninety_day_plan",
            "cross_functional_handoffs",
            "collaboration",
        } <= required_fields
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
    assert RETIRED_BLUEPRINT_IDS.isdisjoint(entries)
    assert all(not (ROOT / blueprint_id).exists() for blueprint_id in RETIRED_BLUEPRINT_IDS)
    assert set(BLUEPRINTS) <= set(entries)
    for blueprint_id in BLUEPRINTS:
        product = entries[blueprint_id]["product"]
        assert entries[blueprint_id]["name"] == PUBLIC_NAMES[blueprint_id]
        assert product["default_demo_business"] == "Bibblio"
        assert product["business_goal"] == "Build a successful business for Bibblio."
        assert product["collaboration_group"] == "business-success-team"
        expected_mcp_collaboration = {
            "enabled": True,
            "goal_id": "bibblio-business-success",
            "path": "/mcp",
            "service_name": "mn-job-collaboration",
            "service_tags": ["mcp", "job-collaboration"],
            "transport": "streamable-http",
        }
        actual_mcp_collaboration = entries[blueprint_id]["mcp_collaboration"]
        assert {
            key: actual_mcp_collaboration[key]
            for key in expected_mcp_collaboration
        } == expected_mcp_collaboration
        assert len(actual_mcp_collaboration["starter_questions"]) >= 3
        if blueprint_id == "gtm_assistant":
            assert actual_mcp_collaboration["starter_questions"] == [
                "How many development emails were sent in this run?",
                "How many matching development replies have been observed?",
                "What should we do next?",
                "What approval do you need before a development email can be sent?",
            ]


def test_knowledge_and_sample_inputs_remain_the_unchanged_bibblio_demo():
    for relative_path, expected_digest in UNCHANGED_DEMO_ASSETS.items():
        actual_digest = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert actual_digest == expected_digest, relative_path


def test_gtm_fixture_is_synthetic_and_mcp_packet_excludes_contact_fields():
    sample_path = ROOT / "growth_partnerships_coworker" / "examples" / "sample_inputs" / "edtech_contacts_sample.csv"
    with sample_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["Email"].endswith("@example.invalid") for row in rows)

    source = (ROOT / "growth_partnerships_coworker" / "payloads" / "domain" / "workers.py").read_text(encoding="utf-8")
    assert '"send_authorized": False' in source
    assert '"private_fields_excluded_from_mcp": ["name", "email", "note", "individual draft body"]' in source


def test_gtm_smtp_defaults_are_disabled_and_contain_no_live_identity_or_secret():
    blueprint = ROOT / "growth_partnerships_coworker"
    config_text = (blueprint / "config" / "default.json").read_text(encoding="utf-8")
    manifest_text = (blueprint / "manifest.json").read_text(encoding="utf-8")
    config = json.loads(config_text)

    assert config["smtp_delivery"] == {
        "enabled": False,
        "mode": "development",
        "host": "smtp.mail.me.com",
        "port": 587,
        "security": "starttls",
        "timeout_seconds": 10,
        "max_messages_per_run": 1,
    }
    assert config["inputs"]["payload"]["email_send_approval"] == {"approved": False}
    assert "@me.com" not in config_text
    assert "@gmail.com" not in config_text
    assert "@me.com" not in manifest_text
    assert "@gmail.com" not in manifest_text


def test_finance_fixture_retains_deterministic_economics():
    payloads = ROOT / "business_finance_coworker" / "payloads"
    previous_domain_modules = [
        name
        for name in sys.modules
        if name == "domain" or name.startswith("domain.")
    ]
    for name in previous_domain_modules:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(payloads))
    try:
        module = importlib.import_module("domain.metrics")
        fixture = json.loads(
            (ROOT / "business_finance_coworker" / "examples" / "sample_inputs" / "business_metrics.json").read_text()
        )
        values = module.calculate_unit_economics(fixture)["metrics"]
    finally:
        sys.path.remove(str(payloads))
        for name in list(sys.modules):
            if name == "domain" or name.startswith("domain."):
                sys.modules.pop(name, None)
    assert values["monthly_revenue"] == 1409.06
    assert values["monthly_contribution_after_fixed_costs_and_acquisition"] == -5300.9332
    assert values["break_even_paying_customers"] == 548


def test_role_specific_safety_fixtures_are_present():
    learning = json.loads(
        (ROOT / "learning_quality_safety_coworker" / "examples" / "sample_inputs" / "content_backlog.json").read_text()
    )
    assert any(item["claim_risk"] == "blocked" for item in learning["items"])

    content = json.loads(
        (ROOT / "content_studio_coworker" / "examples" / "sample_inputs" / "approved_learning_briefs.json").read_text()
    )
    statuses = {item["learning_review_status"] for item in content["briefs"]}
    assert {"PASS", "PASS WITH CONDITIONS", "REVISE"} <= statuses

    with (ROOT / "gtm_assistant" / "examples" / "sample_inputs" / "parent_feedback.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        feedback = list(csv.DictReader(handle))
    assert feedback and all(row["data_status"] == "synthetic_demo" for row in feedback)


def test_founder_brief_preserves_partial_peer_evidence_and_only_keeps_unmet_handoffs(tmp_path):
    payloads = ROOT / "business_finance_coworker" / "payloads"
    for module_name in [name for name in sys.modules if name == "domain" or name.startswith("domain.")]:
        sys.modules.pop(module_name)
    sys.path.insert(0, str(payloads))
    try:
        collaboration = importlib.import_module("domain.collaboration")
        handoffs = [
            {"to": "growth_partnerships_lead", "provides": "finance limits", "needs_from": "channel evidence"},
            {"to": "customer_lifecycle_director", "provides": "retention targets", "needs_from": "retention evidence"},
            {"to": "content_studio_director", "provides": "unit-cost limit", "needs_from": "production evidence"},
            {"to": "learning_quality_safety_director", "provides": "capacity context", "needs_from": "review evidence"},
        ]
        peer_signal = {
            "work_packet_id": "wp-growth",
            "worker": "growth_partnerships_lead",
            "worker_role": "Growth and Partnerships Lead",
            "stage": "publish_gtm_outreach_queue",
            "decision_or_recommendation": "Run the bounded pilot.",
            "confidence": "low",
            "publication_state": "final",
        }
        collaboration.write_final_artifact(
            {
                "run_dir": str(tmp_path),
                "config": {
                    "inputs": {
                        "payload": {
                            "business_name": "Bibblio",
                            "business_goal": "Build a successful business for Bibblio.",
                            "goal_id": "bibblio-business-success",
                            "planning_horizon_days": 90,
                        }
                    }
                },
            },
            {
                "business_goal": "Build a successful business for Bibblio.",
                "goal_id": "bibblio-business-success",
                "work_packet_id": "wp-finance",
                "decision_or_recommendation": "Keep tests cash bounded.",
                "confidence": "low",
                "requested_approval": ["Approve the cash ceiling."],
                "risks": ["Inputs are synthetic."],
                "source_refs": ["input:business_metrics.json"],
            },
            artifact_type="business_finance_control_brief",
            executive_summary="Finance brief.",
            evidence={"status": "synthetic_demo"},
            next_steps=["Reconcile inputs."],
            data_status="synthetic_demo",
            role_contribution="Protect cash.",
            north_star_question="Can retained customers fund delivery?",
            role_scorecard=[{"metric": "monthly_contribution", "current": None}],
            founder_decisions=[{"decision": "Approve the cash ceiling."}],
            cross_functional_handoffs=handoffs,
            ninety_day_plan=[
                {"days": "0-30", "outcome": "Baseline."},
                {"days": "31-60", "outcome": "Measure."},
                {"days": "61-90", "outcome": "Decide."},
            ],
            peer_context={"status": "ok", "signals": [peer_signal], "warnings": []},
        )
        artifact = json.loads((tmp_path / "final_artifact.json").read_text(encoding="utf-8"))
        synthesis = artifact["collaboration"]["team_synthesis"]
        assert artifact["collaboration"]["peer_goal_signals"] == [peer_signal]
        assert synthesis["peer_workers_considered"] == ["growth_partnerships_lead"]
        assert synthesis["unresolved_without_peer_evidence"] == [
            "retention evidence",
            "production evidence",
            "review evidence",
        ]
    finally:
        sys.path.remove(str(payloads))
        for module_name in [name for name in sys.modules if name == "domain" or name.startswith("domain.")]:
            sys.modules.pop(module_name)
