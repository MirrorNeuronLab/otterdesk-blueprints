from __future__ import annotations

import json
from pathlib import Path

from mn_sdk.blueprint_support import deep_merge, manifest_config_defaults


ROOT = Path(__file__).resolve().parents[1]

RAG_BLUEPRINTS = {
    "drug_discovery_research_assistant",
    "financial_advisor",
    "generic_customer_service_voice_coworker",
    "legal_assistant",
    "purchase_research_assistant",
    "cctv_operator",
}

SUPPORTED_KNOWLEDGE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
LEGACY_RAG_BACKENDS = {"redis_vector_rag", "lexical_plain_text", "working_memory_plus_rag"}


def _normalized_rag_snapshot(rag: dict) -> dict:
    normalized = dict(rag)
    if normalized.get("backend") in LEGACY_RAG_BACKENDS:
        normalized["backend"] = "milvus_lite"
    normalized.pop("redis_url", None)
    if normalized.get("enabled") is True:
        normalized["index_on_startup"] = True
    return normalized


def _embedded_manifest_configs(manifest: dict):
    for node in manifest.get("agents", {}).get("nodes", []):
        env = (node.get("config") or {}).get("environment") or {}
        if env.get("MN_BLUEPRINT_CONFIG_JSON"):
            yield json.loads(env["MN_BLUEPRINT_CONFIG_JSON"])
    for template in manifest.get("metadata", {}).get("agent_templates", {}).get("nodes", []):
        env = (template.get("with") or {}).get("environment") or {}
        if env.get("MN_BLUEPRINT_CONFIG_JSON"):
            yield json.loads(env["MN_BLUEPRINT_CONFIG_JSON"])


def _knowledge_source_dir(blueprint_dir: Path, manifest: dict, knowledge_rag: dict) -> Path:
    configured = blueprint_dir / str(knowledge_rag["knowledge_dir"])
    if configured.is_dir():
        return configured
    resources = manifest.get("metadata", {}).get("job_data", {}).get("resources", [])
    knowledge = next(
        (
            resource
            for resource in resources
            if isinstance(resource, dict) and resource.get("name") == "knowledge"
        ),
        {},
    )
    seed = str(knowledge.get("seed") or "")
    assert seed.startswith("@/"), blueprint_dir.name
    return blueprint_dir / seed.removeprefix("@/")


def test_non_vc_blueprints_declare_grounded_rag_and_agentic_tool_contracts():
    for blueprint_id in sorted(RAG_BLUEPRINTS):
        blueprint_dir = ROOT / blueprint_id
        manifest = json.loads((blueprint_dir / "manifest.json").read_text(encoding="utf-8"))
        config = deep_merge(
            manifest_config_defaults(manifest),
            json.loads(
                (blueprint_dir / "config" / "default.json").read_text(encoding="utf-8")
            ),
        )

        knowledge_rag = config.get("knowledge_rag")
        assert isinstance(knowledge_rag, dict), blueprint_id
        assert knowledge_rag["enabled"] is True, blueprint_id
        assert knowledge_rag["required"] is False, blueprint_id
        assert knowledge_rag["purpose"], blueprint_id
        assert knowledge_rag["grounding_policy"], blueprint_id
        assert len(knowledge_rag.get("retrieval_targets") or []) >= 3, blueprint_id
        knowledge_dir = _knowledge_source_dir(blueprint_dir, manifest, knowledge_rag)
        assert knowledge_dir.exists(), blueprint_id
        assert any(path.suffix in SUPPORTED_KNOWLEDGE_SUFFIXES for path in knowledge_dir.rglob("*") if path.is_file()), blueprint_id

        agentic = config.get("agentic_research")
        assert isinstance(agentic, dict), blueprint_id
        assert agentic["enabled"] is True, blueprint_id
        assert agentic["max_iterations_per_agent"] == 1, blueprint_id
        assert agentic["max_tool_calls_per_agent"] == 2, blueprint_id
        assert "finish" in agentic["allowed_tools"], blueprint_id
        assert len(agentic["allowed_tools"]) >= 4, blueprint_id
        llm_agents = set((config.get("llm") or {}).get("agents") or {})
        assert set(agentic["agent_ids"]) <= llm_agents, blueprint_id

        expected_rag_snapshot = _normalized_rag_snapshot(knowledge_rag)
        assert _normalized_rag_snapshot(manifest.get("knowledge_rag")) == expected_rag_snapshot, blueprint_id
        assert manifest.get("agentic_research") == agentic, blueprint_id

        for section_list in (
            config["interfaces"]["config"],
            config["interfaces"]["config_sections"],
        ):
            assert "knowledge_rag" in section_list, blueprint_id
            assert "agentic_research" in section_list, blueprint_id

        for embedded in _embedded_manifest_configs(manifest):
            assert _normalized_rag_snapshot(embedded.get("knowledge_rag")) == expected_rag_snapshot, blueprint_id
            assert embedded.get("agentic_research") == agentic, blueprint_id
