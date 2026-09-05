from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from blueprint_modernization_support import blueprint_path
from mn_sdk.blueprints import (
    blueprint_definition,
    read_blueprint,
    read_catalog,
    resolve_config,
)
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
for source in sorted((WORKSPACE / "mn-skills").glob("*/src")):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

BLUEPRINTS = {
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
    "gtm_assistant/examples/sample_inputs/SAMPLE_DATASET_MANIFEST.json": "3bfea624c7279aa87aa9747658c27fffc8e90d75a3d900e56c6042f20e396cfd",
    "gtm_assistant/examples/sample_inputs/parent_feedback.csv": "6e490348b8e4c4b140c559b1c5e4bbdc316af2cc37df667e0ab55dec0f84b5bd",
    "gtm_assistant/payloads/knowledge/parent_lifecycle_playbook.md": "d2506c08e13a2e4218db698aa2aacc0e9fb9606fe7941985c8778ace6cf893a9",
}


def test_published_business_blueprints_share_one_goal_contract():
    for blueprint_id, (agent_id, step_ids) in BLUEPRINTS.items():
        manifest = blueprint_definition(
            read_blueprint(blueprint_path(blueprint_id) / "manifest.json")
        )
        assert manifest["identity"]["id"] == blueprint_id
        assert manifest["identity"]["name"] == PUBLIC_NAMES[blueprint_id]
        assert "Bibblio" not in manifest["identity"]["name"]
        assert (
            manifest["metadata"]["business_goal"]
            == "Build a successful business for Bibblio."
        )
        assert manifest["metadata"]["collaboration_group"] == "business-success-team"
        expected_agent_ids = [agent_id] if isinstance(agent_id, str) else agent_id
        assert list(manifest["agents"]["registry"]) == expected_agent_ids
        assert [step["id"] for step in manifest["workflow"]["steps"]] == step_ids
        assert manifest["workflow"]["steps"][1]["needs"] == [step_ids[0]]
        if blueprint_id == "gtm_assistant":
            assert manifest["identity"]["version"] == 1
            assert manifest["workflow"]["workflow_id"] == "gtm_assistant_v4"
            assert manifest["workflow"]["steps"][2]["needs"] == [step_ids[1]]
            assert (
                manifest["workflow"]["steps"][2]["control"]["retry"]["max_attempts"]
                == 1
            )
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
        config = resolve_config(read_blueprint(blueprint_path(blueprint_id))).data
        dependency_names = {
            dependency["name"] for dependency in manifest["skill_dependencies"]
        }
        assert manifest["response_service"] == {"enabled": True}
        assert "mcp_collaboration" not in manifest
        assert "mirrorneuron-job-response-skill" in dependency_names
        assert "mirrorneuron-rag-skill" in dependency_names
        assert "mirrorneuron-mcp-server-skill" not in dependency_names
        assert "mirrorneuron-mcp-client-skill" in dependency_names
        assert "auxiliary_entrypoints" not in manifest["agents"]
        assert "extra_nodes" not in manifest["agents"]
        assert config["knowledge_rag"]["backend"] == "milvus_lite"
        assert "mcp_collaboration" not in config
        assert "peer_mcp_servers" not in config["inputs"]["payload"]
        assert config["inputs"]["payload"]["business_name"] == "Bibblio"
        assert config["inputs"]["payload"]["planning_horizon_days"] == 90
        required_fields = set(
            manifest["contracts"]["outputs"]["primary"]["required_fields"]
        )
        assert {
            "role_contribution",
            "north_star_question",
            "role_scorecard",
            "founder_decisions",
            "ninety_day_plan",
            "cross_functional_handoffs",
            "job_context",
        } <= required_fields
        assert (blueprint_path(blueprint_id) / "payloads" / "prompts").is_dir()


def test_catalog_replaces_the_monolith_with_five_collaboration_group_members():
    entries = {entry["id"]: entry for entry in read_catalog(ROOT / "index.json")}
    assert "bibblio_profitability_workforce" not in entries
    assert RETIRED_BLUEPRINT_IDS.isdisjoint(entries)
    assert all(
        not (blueprint_path(blueprint_id)).exists()
        for blueprint_id in RETIRED_BLUEPRINT_IDS
    )
    assert set(BLUEPRINTS) <= set(entries)
    for blueprint_id in BLUEPRINTS:
        product = entries[blueprint_id]["product"]
        assert entries[blueprint_id]["name"] == PUBLIC_NAMES[blueprint_id]
        assert product["default_demo_business"] == "Bibblio"
        assert product["business_goal"] == "Build a successful business for Bibblio."
        assert product["collaboration_group"] == "business-success-team"
        assert entries[blueprint_id]["response_service"] == {"enabled": True}
        assert "mcp_collaboration" not in entries[blueprint_id]
        assert len(entries[blueprint_id]["starter_questions"]) >= 3


def test_knowledge_and_sample_inputs_remain_the_unchanged_bibblio_demo():
    for relative_path, expected_digest in UNCHANGED_DEMO_ASSETS.items():
        actual_digest = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert actual_digest == expected_digest, relative_path
