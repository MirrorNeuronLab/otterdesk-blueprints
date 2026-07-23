from __future__ import annotations

import json
from pathlib import Path

from otterdesk_blueprint_suite import (
    test_all_blueprints_declare_actor_style_llm_config,
    test_batch_blueprints_declare_advisory_schedules,
    test_index_entries_point_to_loadable_blueprint_folders,
    test_otterdesk_blueprints_are_workflow_driven_manifests,
    test_otterdesk_blueprints_declare_membrane_context_memory_layer,
    test_otterdesk_blueprints_declare_product_experience_contracts,
    test_otterdesk_manifests_pin_gar_skill_dependencies,
    test_otterdesk_completion_contract_is_explicit_and_terminal_sinks_are_reachable,
    test_otterdesk_json_uses_python311_for_host_python_commands,
    test_otterdesk_manifests_require_runtime_workflow_control_contract,
    test_otterdesk_nodes_use_shared_agent_templates_and_render,
    test_otterdesk_rendered_completion_contract_is_valid,
    test_otterdesk_topology_metadata_matches_runtime_nodes,
    test_otterdesk_workflow_steps_are_bounded_and_retryable,
    test_video_gpu_blueprints_declare_hard_nvidia_cuda_requirements_consistently,
)


RAG_BLUEPRINTS = {
    "cctv_operator",
    "drug_discovery_research_assistant",
    "financial_advisor",
    "generic_customer_service_voice_coworker",
    "legal_assistant",
    "purchase_research_assistant",
    "research_coscientist",
    "vc_assistant",
}


def test_rag_blueprints_declare_job_scoped_knowledge_database_and_state_resources():
    root = Path(__file__).resolve().parents[1]

    for blueprint_id in sorted(RAG_BLUEPRINTS):
        manifest = json.loads((root / blueprint_id / "manifest.json").read_text(encoding="utf-8"))
        resources = manifest["metadata"]["job_data"]["resources"]
        by_name = {resource["name"]: resource for resource in resources}

        assert set(by_name) == {"knowledge", "rag", "state"}, blueprint_id
        assert by_name["knowledge"]["path"] == "knowledge", blueprint_id
        assert by_name["rag"]["path"] == "databases/rag", blueprint_id
        assert by_name["state"]["path"] == "state", blueprint_id
        assert all(resource["access"] == "read_write" for resource in resources), blueprint_id

        seed = by_name["knowledge"].get("seed")
        if seed:
            assert seed.startswith("@/payloads/"), blueprint_id
            assert (root / blueprint_id / seed.removeprefix("@/")).is_dir(), blueprint_id
