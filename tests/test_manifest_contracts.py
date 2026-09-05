from __future__ import annotations

from pathlib import Path

from blueprint_modernization_support import blueprint_path
from mn_sdk.blueprints import (
    blueprint_definition,
    read_blueprint,
    read_catalog,
)

RAG_BLUEPRINTS = {
    "cctv_operator",
    "drug_discovery_research_assistant",
    "financial_advisor",
    "gtm_assistant",
    "legal_assistant",
    "microduck_controller",
    "purchasing_manager",
    "research_assistant",
    "ros_amr_controller",
    "vc_assistant",
}


def test_catalog_blueprints_declare_job_response_service():
    root = Path(__file__).resolve().parents[1]
    entries = read_catalog(root / "index.json")

    assert entries
    for entry in entries:
        blueprint_id = entry["id"]
        manifest = blueprint_definition(
            read_blueprint(root / entry["path"] / "manifest.json")
        )
        assert entry["response_service"] == manifest["response_service"], blueprint_id
        assert manifest["response_service"]["enabled"] is True, blueprint_id
        if blueprint_id in {"microduck_controller", "ros_amr_controller"}:
            assert manifest["response_service"]["agent"]["kind"] == "bounded_mcp"
        else:
            assert manifest["response_service"] == {"enabled": True}, blueprint_id
        assert "mcp_collaboration" not in entry, blueprint_id
        assert "mcp_collaboration" not in manifest, blueprint_id
        assert len(entry["starter_questions"]) >= 3, blueprint_id
        assert "response_service" not in manifest["workflow"], blueprint_id
        assert "response_service" not in manifest["agents"], blueprint_id
        assert (
            "services" not in manifest or "response_service" not in manifest["services"]
        ), blueprint_id


def test_source_manifests_use_current_runtime_envelope_version():
    root = Path(__file__).resolve().parents[1]
    entries = read_catalog(root / "index.json")

    for entry in entries:
        manifest = blueprint_definition(
            read_blueprint(root / entry["path"] / "manifest.json")
        )
        assert manifest["apiVersion"] == "mn.workflow/v1", entry["id"]
        assert read_blueprint(root / entry["path"]).manifest["version"] == "1.0.0"


def test_rag_blueprints_declare_job_scoped_knowledge_database_and_state_resources():

    for blueprint_id in sorted(RAG_BLUEPRINTS):
        manifest = blueprint_definition(
            read_blueprint(blueprint_path(blueprint_id) / "manifest.json")
        )
        resources = manifest["metadata"]["job_data"]["resources"]
        by_name = {resource["name"]: resource for resource in resources}

        assert set(by_name) == {"knowledge", "rag", "state"}, blueprint_id
        assert by_name["knowledge"]["path"] == "knowledge", blueprint_id
        assert by_name["rag"]["path"] == "databases/rag", blueprint_id
        assert by_name["state"]["path"] == "state", blueprint_id
        assert all(resource["access"] == "read_write" for resource in resources), (
            blueprint_id
        )

        seed = by_name["knowledge"].get("seed")
        if seed:
            assert seed.startswith("@/payloads/"), blueprint_id
            assert (blueprint_path(blueprint_id) / seed.removeprefix("@/")).is_dir(), (
                blueprint_id
            )
