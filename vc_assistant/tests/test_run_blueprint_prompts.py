from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

import pytest

from mn_sdk.blueprint_support import BlueprintBundleLayout, default_config_path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "payloads" / "runtime" / "runtime.py"
BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
for skill_name in (
    "evidence_engine_skill",
    "actor_review_skill",
    "client_report_skill",
    "document_reading_skill",
    "public_research_orchestrator_skill",
    "scoring_framework_skill",
):
    skill_src = BLUEPRINT_DIR.parents[1] / "mn-skills" / skill_name / "src"
    if skill_src.exists():
        sys.path.insert(0, str(skill_src))


def load_module():
    spec = importlib.util.spec_from_file_location("vc_runtime", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_source_manifest_keeps_the_default_runtime_declarative():
    default_config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text())
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    assert manifest["apiVersion"] == "mn.workflow.source/v2"
    assert manifest["agents"] == {"extra_templates": manifest["agents"]["extra_templates"], "extra_edges": manifest["agents"]["extra_edges"]}
    assert manifest["workflow"]["steps"][0]["id"] == "startup_folder_watcher"
    assert default_config["llm"]["model"] == "default"


def test_manifest_steps_resolve_to_conventional_behavior_modules():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    handlers = {step["run"]["handler"] for step in manifest["workflow"]["steps"]}

    assert handlers == {
        "steps.intake",
        "steps.evidence",
        "steps.research",
        "steps.scoring",
        "steps.reporting",
    }
    assert all(":" not in handler for handler in handlers)


def test_runtime_module_resolves_the_blueprint_root_after_the_entrypoint_move():
    runner = load_module()
    layout = BlueprintBundleLayout.discover(SCRIPT_PATH)

    assert layout.root == BLUEPRINT_DIR
    assert layout.payload_root == BLUEPRINT_DIR / "payloads"
    assert default_config_path(SCRIPT_PATH) == BLUEPRINT_DIR / "config" / "default.json"
    assert runner.PROMPTS.prompt_dir == BLUEPRINT_DIR / "payloads" / "prompts"


def test_vc_has_no_local_blueprint_entrypoint_or_generic_dispatch():
    runtime_source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert not (SCRIPT_PATH.parent / "run_blueprint.py").exists()
    assert "def run_blueprint(" not in runtime_source
    assert "def execute_runtime_handler(" not in runtime_source
    assert "globals().update(" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in (BLUEPRINT_DIR / "payloads" / "agents").glob("*.py")
    )


def test_model_contract_uses_the_shared_adaptive_default():
    default_config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text())
    llm = default_config["llm"]

    assert llm["model"] == "default"
    assert "model" not in llm["configs"]["primary"]
    assert "small_model_profile" not in llm
    assert "large_model_profile" not in llm


def test_method_score_state_merges_independent_scorer_outputs(tmp_path):
    rb = load_module()
    rb.write_company_method_scores_state(
        tmp_path,
        "Acme",
        {"berkus_method": {"method_id": "berkus_method", "score": 1}},
    )
    rb.write_company_method_score_state(
        tmp_path,
        "Acme",
        "scorecard_bill_payne_method",
        {"method_id": "scorecard_bill_payne_method", "score": 2},
    )
    rb.write_company_method_score_state(
        tmp_path,
        "Acme",
        "berkus_method",
        {"method_id": "berkus_method", "score": 3},
    )

    methods = rb.read_company_method_scores_state(tmp_path, "Acme")

    assert methods["berkus_method"]["score"] == 3
    assert methods["scorecard_bill_payne_method"]["score"] == 2


def test_research_prompt_specs_are_distinct_for_all_agent_ids():
    rb = load_module()
    agent_ids = [
        "research_planner",
        "company_identity_researcher",
        "funding_researcher",
        "market_comp_researcher",
        "traction_verifier",
        "rendered_page_researcher",
    ]
    specs = {agent_id: rb.research_prompt_spec(agent_id) for agent_id in agent_ids}

    assert set(specs) == set(agent_ids)
    assert len({spec["mission"] for spec in specs.values()}) == len(agent_ids)
    assert "public funding" in specs["funding_researcher"]["mission"].lower()
    assert "rendered" in specs["rendered_page_researcher"]["mission"].lower()


def test_research_prompts_include_stage_specific_rag_and_tool_policy():
    rb = load_module()
    plan = {"stage_queries": {"funding_researcher": ["Acme funding"]}, "lanes": [], "signals": {}, "privacy_policy": "public-safe"}
    rag_context = {"status": "ready", "context": "Funding playbook", "citations": [{"ref": 1}]}
    system_prompt, prompt = rb.build_research_agent_prompt(
        company="Acme",
        stage="funding_researcher",
        plan=plan,
        internet={},
        allowed_tools={"browser_search", "finish"},
        remaining_tool_calls=2,
        rag_context=rag_context,
        knowledge_rag={"enabled": True, "status": "ready", "config": {"required": True}},
        observations=[],
    )

    assert "funding_researcher" in system_prompt
    assert "Pitch claim treated as public confirmation" in prompt["failure_conditions"]
    assert prompt["rag_refs_required"] is True
    assert prompt["required_schema"]["tool_calls"][0]["rag_refs"]


def test_actor_review_prompts_are_role_specific():
    rb = load_module()
    context = {"rag_context": {"citations": [{"ref": 1}]}, "company_summaries": []}
    scorer_prompt = rb.build_actor_review_prompt(
        actor_id="berkus_scorer",
        actor_spec={"role": "Berkus Scorer"},
        context=context,
        knowledge_rag={"enabled": True, "status": "ready", "config": {"required": False}},
    )[1]
    writer_prompt = rb.build_actor_review_prompt(
        actor_id="company_report_writer",
        actor_spec={"role": "Company Report Writer"},
        context=context,
        knowledge_rag={"enabled": True, "status": "ready", "config": {"required": False}},
    )[1]

    assert scorer_prompt["task"] != writer_prompt["task"]
    assert "berkus_method" in scorer_prompt["focus"]
    assert "evidence traceability" in writer_prompt["focus"]


def test_required_rag_zero_citations_fails_before_llm(monkeypatch):
    rb = load_module()
    calls = {"llm": 0}

    def fake_load_rag_skill():
        return None

    def fake_require_ready(state, *, stage="", company="", context=None, min_citations=0):
        if min_citations and not (context or {}).get("citations"):
            raise RuntimeError("required RAG returned zero citations")
        return context if context is not None else state

    class SpyLLM:
        def generate_json(self, **kwargs):
            calls["llm"] += 1
            return {"tool_calls": [{"tool": "finish"}], "rag_refs": [1]}

    monkeypatch.setattr(rb, "_load_rag_skill", fake_load_rag_skill)
    monkeypatch.setattr(rb, "skill_require_ready_knowledge_rag", fake_require_ready)
    monkeypatch.setattr(
        rb,
        "retrieve_knowledge_rag_context",
        lambda **kwargs: {"enabled": True, "status": "ready", "context": "", "citations": [], "chunks": []},
    )

    with pytest.raises(RuntimeError, match="zero citations"):
        rb.run_agentic_research_stage(
            company="Acme",
            stage="funding_researcher",
            plan={"stage_queries": {"funding_researcher": ["Acme funding"]}, "queries": ["Acme"], "lanes": []},
            internet={},
            run_dir=None,
            action_budget=None,
            llm=SpyLLM(),
            agentic={"allowed_tools": ["finish"], "max_iterations_per_agent": 1, "max_tool_calls_per_agent": 1},
            trace=[],
            knowledge_rag={"enabled": True, "status": "ready", "config": {"required": True}},
        )

    assert calls["llm"] == 0


def test_blank_knowledge_rag_db_root_uses_runtime_rag_env(monkeypatch):
    rb = load_module()
    db_root = "/tmp/mn-rag"
    config = {"knowledge_rag": {"enabled": True, "db_root": "", "namespace": "vc"}}

    monkeypatch.setenv("MN_RAG_DB_ROOT", db_root)
    monkeypatch.setenv("MN_REDIS_URL", "redis://:secret@redis:6379/0")

    patched = rb.with_runtime_knowledge_rag_defaults(config)

    assert patched["knowledge_rag"]["backend"] == "milvus_lite"
    assert patched["knowledge_rag"]["db_root"] == db_root
    assert patched["knowledge_rag"]["namespace"] == "vc"
    assert "redis_url" not in patched["knowledge_rag"]
    assert config["knowledge_rag"]["db_root"] == ""


def test_explicit_knowledge_rag_db_path_is_preserved(monkeypatch):
    rb = load_module()
    config = {
        "knowledge_rag": {
            "enabled": True,
            "backend": "milvus_lite",
            "db_root": "/explicit/root",
            "db_path": "/explicit/root/vc.db",
        }
    }

    monkeypatch.setenv("MN_RAG_DB_ROOT", "/runtime/root")
    monkeypatch.setenv("MN_REDIS_URL", "redis://:secret@192.168.4.51:56379/0")

    assert rb.with_runtime_knowledge_rag_defaults(config) is config
    assert config["knowledge_rag"]["db_root"] == "/explicit/root"
    assert config["knowledge_rag"]["db_path"] == "/explicit/root/vc.db"
    assert "redis_url" not in config["knowledge_rag"]


def test_agentic_rag_query_prioritizes_stage_playbook_terms(monkeypatch):
    rb = load_module()
    captured: dict[str, str] = {}

    def fake_load_rag_skill():
        return None

    def fake_require_ready(state, *, stage="", company="", context=None, min_citations=0):
        return context if context is not None else state

    def fake_retrieve(**kwargs):
        captured["query"] = kwargs["query"]
        return {
            "enabled": True,
            "status": "ready",
            "context": "Research planner playbook context.",
            "citations": [{"ref": 1, "chunk_id": "planner"}],
            "chunks": [{"chunk_id": "planner"}],
        }

    class FinishLLM:
        def generate_json(self, **kwargs):
            return {"tool_calls": [{"tool": "finish", "reason": "stage guidance reviewed"}], "rag_refs": [1]}

    monkeypatch.setattr(rb, "_load_rag_skill", fake_load_rag_skill)
    monkeypatch.setattr(rb, "skill_require_ready_knowledge_rag", fake_require_ready)
    monkeypatch.setattr(rb, "retrieve_knowledge_rag_context", fake_retrieve)

    rb.run_agentic_research_stage(
        company="Aurora Ai",
        stage="research_planner",
        plan={
            "stage_queries": {"research_planner": ["Aurora Ai company website Crunchbase public profile"]},
            "queries": ["Aurora Ai startup public evidence"],
            "lanes": [{"lane_id": "fundraising"}],
        },
        internet={},
        run_dir=None,
        action_budget=None,
        llm=FinishLLM(),
        agentic={"allowed_tools": ["finish"], "max_iterations_per_agent": 1, "max_tool_calls_per_agent": 1},
        trace=[],
        knowledge_rag={"enabled": True, "status": "ready", "config": {"required": True}},
    )

    assert "VC diligence lane planning" in captured["query"]
    assert "public-safe startup research" in captured["query"]
    assert "fundraising" in captured["query"]
    assert not captured["query"].startswith("Aurora Ai")


def test_funding_researcher_uses_agentic_path(monkeypatch):
    rb = load_module()
    called: list[str] = []

    def fake_agentic(**kwargs):
        called.append(kwargs["stage"])
        return kwargs["stage"], []

    monkeypatch.setattr(rb, "run_agentic_research_stage", fake_agentic)
    monkeypatch.setattr(rb, "_research_one_stage", lambda company, stage, query, plan, internet, run_dir, action_budget: (stage, []))

    rb.research_company_by_stage(
        "Acme",
        {
            "internet_research": {"enabled": True, "max_stage_workers": 1},
            "agentic_research": {"enabled": True, "agent_ids": ["funding_researcher"]},
        },
        llm=object(),
    )

    assert called == ["funding_researcher"]


def test_agentic_stage_gap_fill_runs_deterministic_research(monkeypatch):
    rb = load_module()
    deterministic_calls: list[str] = []

    def fake_agentic(**kwargs):
        return kwargs["stage"], [
            rb._source_record(
                company=kwargs["company"],
                query="Acme funding",
                url="research_plan",
                title="planned",
                snippet="planned",
                status="planned",
                skill="research_planner",
                verification_target=kwargs["stage"],
            )
        ]

    def fake_one_stage(company, stage, query, plan, internet, run_dir, action_budget):
        deterministic_calls.append(stage)
        return stage, [
            rb._source_record(
                company=company,
                query="Acme funding",
                url="https://acme.example/funding",
                title="Acme funding",
                snippet="Public funding confirmation.",
                status="ok",
                skill="python_http_fallback",
                verification_target=stage,
            )
        ]

    monkeypatch.setattr(rb, "run_agentic_research_stage", fake_agentic)
    monkeypatch.setattr(rb, "_research_one_stage", fake_one_stage)

    by_stage = rb.research_company_by_stage(
        "Acme",
        {
            "internet_research": {"enabled": True, "max_stage_workers": 1},
            "agentic_research": {"enabled": True, "agent_ids": ["funding_researcher"]},
        },
        llm=object(),
    )

    assert deterministic_calls.count("funding_researcher") == 1
    assert any(source.get("fallback_after_agentic") is True for source in by_stage["funding_researcher"])
    assert any(rb.is_substantive_public_source(source) for source in by_stage["funding_researcher"])


def test_company_evidence_summaries_include_counts_and_source_quality():
    rb = load_module()
    summaries = rb.build_company_evidence_summaries(
        analyses=[
            {
                "company_name": "Acme",
                "company_slug": "acme",
                "evidence_summary": {"missing_methods": ["cost_to_duplicate_method"]},
            }
        ],
        company_records={
            "Acme": [
                {
                    "filename": "pitch.txt",
                    "suffix": ".txt",
                    "sha256": "abcdef1234567890",
                    "character_count": 500,
                    "extraction_method": "embedded_text",
                    "warnings": [],
                }
            ]
        },
        research_ledgers={
            "Acme": {
                "company_identity_researcher": [
                    {
                        "url": "https://acme.example",
                        "title": "Acme",
                        "snippet": "Official product page",
                        "status": "ok",
                        "source_quality_label": "public_confirmation",
                        "verification_target": "company_identity_researcher",
                    }
                ]
            }
        },
    )

    assert summaries[0]["local_evidence"]["record_count"] == 1
    assert summaries[0]["research_sources"]["substantive_source_count"] == 1
    assert summaries[0]["research_sources"]["source_quality_counts"]["public_confirmation"] == 1
    assert summaries[0]["missing_methods"] == ["cost_to_duplicate_method"]


def test_transport_keeps_compact_company_evidence_but_omits_top_level_raw_fields():
    rb = load_module()
    artifact = {
        "evidence": [{"text_preview": "top level raw"}],
        "research_sources": [{"snippet": "top level raw"}],
        "action_ledger": {"used": 1, "actions": [{"tool": "x"}]},
        "company_reports": [
            {
                "company_name": "Acme",
                "company_slug": "acme",
                "evidence": [
                    {
                        "filename": "pitch.txt",
                        "suffix": ".txt",
                        "sha256": "abcdef1234567890",
                        "character_count": 1200,
                        "extraction_method": "embedded_text",
                        "warnings": ["ok"],
                        "text_preview": "local business evidence " * 100,
                    }
                ],
                "research_sources": [
                    {
                        "company": "Acme",
                        "query": "Acme funding",
                        "url": "https://acme.example/funding",
                        "title": "Acme funding",
                        "snippet": "public evidence " * 200,
                        "status": "ok",
                        "skill": "python_http_fallback",
                        "verification_target": "funding_researcher",
                        "source_quality_label": "public_confirmation",
                    }
                ],
            }
        ],
    }

    transport = rb.final_artifact_for_transport(artifact)

    assert "evidence" not in transport
    assert "research_sources" not in transport
    assert "actions" not in transport["action_ledger"]
    report = transport["company_reports"][0]
    assert report["evidence"][0]["filename"] == "pitch.txt"
    assert len(report["evidence"][0]["text_preview"]) <= rb.MAX_TRANSPORT_TEXT_PREVIEW_CHARS + 20
    assert report["research_sources"][0]["url"] == "https://acme.example/funding"
    assert len(report["research_sources"][0]["snippet"]) <= rb.MAX_TRANSPORT_SNIPPET_CHARS + 20


def test_require_live_llm_rejects_fallback_provider():
    rb = load_module()

    class Budget:
        def start(self, **kwargs):
            return {"status": "running"}

        def complete(self, action, status, metadata=None):
            action["status"] = status

        def summary(self, *, include_actions=True):
            return {"budget": 1, "used": 0, "remaining": 1, "exhausted": False}

    class FakeLLM:
        provider = "fallback"
        model = "fake"

        def generate_json(self, **kwargs):
            return {"provider": "fallback", "summary": "fake", "rag_refs": [1]}

    llm = rb.BudgetedLLM(FakeLLM(), Budget(), require_live=True)

    with pytest.raises(RuntimeError, match="non-live provider"):
        llm.generate_json(system_prompt="actor", user_prompt="{}", fallback={"actor_id": "actor"})
