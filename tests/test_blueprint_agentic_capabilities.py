from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RAG_BLUEPRINTS = {
    "drug_discovery_research_assistant",
    "generic_customer_service_voice_coworker",
    "invoice_bill_extraction_assistant",
    "legal_contract_clause_review_assistant",
    "medical_deid_record_intake_assistant",
    "personal_financial_advisor",
    "personal_income_tax_expert",
    "portfolio_risk_review_assistant",
    "property_deal_research_assistant",
    "safety_video_analyser",
    "tax_form_ocr_capture_assistant",
    "video_watch_assistant",
}

SUPPORTED_KNOWLEDGE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}


def _embedded_manifest_configs(manifest: dict):
    for node in manifest.get("agents", {}).get("nodes", []):
        env = (node.get("config") or {}).get("environment") or {}
        if env.get("MN_BLUEPRINT_CONFIG_JSON"):
            yield json.loads(env["MN_BLUEPRINT_CONFIG_JSON"])
    for template in manifest.get("metadata", {}).get("agent_templates", {}).get("nodes", []):
        env = (template.get("with") or {}).get("environment") or {}
        if env.get("MN_BLUEPRINT_CONFIG_JSON"):
            yield json.loads(env["MN_BLUEPRINT_CONFIG_JSON"])


def test_non_vc_blueprints_declare_grounded_rag_and_agentic_tool_contracts():
    for blueprint_id in sorted(RAG_BLUEPRINTS):
        blueprint_dir = ROOT / blueprint_id
        config = json.loads((blueprint_dir / "config" / "default.json").read_text(encoding="utf-8"))
        manifest = json.loads((blueprint_dir / "manifest.json").read_text(encoding="utf-8"))

        knowledge_rag = config.get("knowledge_rag")
        assert isinstance(knowledge_rag, dict), blueprint_id
        assert knowledge_rag["enabled"] is True, blueprint_id
        assert knowledge_rag["required"] is False, blueprint_id
        assert knowledge_rag["purpose"], blueprint_id
        assert knowledge_rag["grounding_policy"], blueprint_id
        assert len(knowledge_rag.get("retrieval_targets") or []) >= 3, blueprint_id
        knowledge_dir = blueprint_dir / knowledge_rag["knowledge_dir"]
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

        assert manifest.get("knowledge_rag") == knowledge_rag, blueprint_id
        assert manifest.get("agentic_research") == agentic, blueprint_id
        assert manifest["metadata"]["knowledge_rag"] == knowledge_rag, blueprint_id
        assert manifest["metadata"]["agentic_research"] == agentic, blueprint_id

        for section_list in (
            config["interfaces"]["config"],
            config["interfaces"]["config_sections"],
            manifest["metadata"]["interfaces"]["config"],
            manifest["metadata"]["interfaces"]["config_sections"],
        ):
            assert "knowledge_rag" in section_list, blueprint_id
            assert "agentic_research" in section_list, blueprint_id

        for embedded in _embedded_manifest_configs(manifest):
            assert embedded.get("knowledge_rag") == knowledge_rag, blueprint_id
            assert embedded.get("agentic_research") == agentic, blueprint_id
