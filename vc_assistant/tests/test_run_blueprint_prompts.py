from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"


def load_module():
    spec = importlib.util.spec_from_file_location("vc_run_blueprint", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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


def test_require_live_llm_rejects_fallback_provider():
    rb = load_module()

    class Budget:
        def start(self, **kwargs):
            return {"status": "running"}

        def complete(self, action, status, metadata=None):
            action["status"] = status

    class FakeLLM:
        provider = "fallback"
        model = "fake"

        def generate_json(self, **kwargs):
            return {"provider": "fallback", "summary": "fake", "rag_refs": [1]}

    llm = rb.BudgetedLLM(FakeLLM(), Budget(), require_live=True)

    with pytest.raises(RuntimeError, match="non-live provider"):
        llm.generate_json(system_prompt="actor", user_prompt="{}", fallback={"actor_id": "actor"})
