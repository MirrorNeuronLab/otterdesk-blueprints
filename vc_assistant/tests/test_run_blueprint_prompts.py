from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path

import pytest

from vc_assistant.domain_test_support import load_domain_test_surface

from mn_sdk import expand_manifest_source
from mn_sdk.blueprint_support import (
    BlueprintBundleLayout,
    default_config_path,
    load_runtime_config,
)
from mn_sdk.step_runtime import StepContext, resolve_handler

BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
PAYLOAD_DIR = BLUEPRINT_DIR / "payloads"
RUNTIME_PATH = PAYLOAD_DIR / "runtime" / "runtime.py"
sys.path.insert(0, str(PAYLOAD_DIR))
for skill_name in (
    "evidence_engine_skill",
    "actor_review_skill",
    "client_report_skill",
    "document_reading_skill",
    "public_research_orchestrator_skill",
    "rag_skill",
    "scoring_framework_skill",
):
    skill_src = BLUEPRINT_DIR.parents[1] / "mn-skills" / skill_name / "src"
    if skill_src.exists():
        sys.path.insert(0, str(skill_src))
for agent_name in (
    "prototype_bounded_tool_loop_agent",
    "prototype_actor_review_agent",
    "prototype_artifact_finalizer_agent",
    "prototype_entity_queue_agent",
    "prototype_stateful_step_agent",
):
    agent_src = BLUEPRINT_DIR.parents[1] / "mn-agents" / agent_name / "src"
    if agent_src.exists():
        sys.path.insert(0, str(agent_src))


def load_module():
    return load_domain_test_surface(BLUEPRINT_DIR)


def test_source_manifest_keeps_the_default_runtime_declarative():
    default_config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text())
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    assert manifest["apiVersion"] == "mn.workflow.source/v2"
    assert manifest["agents"] == {"registry": manifest["agents"]["registry"]}
    assert manifest["workflow"]["steps"][0]["id"] == "detect_packet_changes"
    assert all(step["run"]["definition"] for step in manifest["workflow"]["steps"])
    assert set(default_config["llm"]) == {"strict_json", "configs", "require_live"}
    assert "agentic_research" not in default_config
    assert default_config["knowledge_rag"] == {"backend": "milvus_lite"}
    assert "resources" not in default_config
    assert "human_control" not in default_config
    assert "input_adapters" not in default_config["interfaces"]
    assert "monitoring" not in default_config["inputs"]["payload"]
    assert "identity" not in default_config

    resolved = load_runtime_config(RUNTIME_PATH)
    assert resolved["identity"] == {
        "blueprint_id": manifest["identity"]["id"],
        "name": manifest["identity"]["name"],
    }
    assert resolved["llm"]["model"] == "default"
    assert resolved["agentic_research"] == manifest["agentic_research"]
    assert resolved["knowledge_rag"]["knowledge_dir"] == "@/payloads/knowledge"
    assert resolved["resources"] == manifest["requirements"]
    assert resolved["human_control"] == manifest["workflow"]["policy"]["human"]
    assert (
        resolved["interfaces"]["input_adapters"]
        == manifest["contracts"]["input_adapters"]["supported"]
    )
    assert (
        resolved["inputs"]["payload"]["monitoring"]
        == manifest["contracts"]["inputs"]["monitoring"]["example"]
    )
    assert set(resolved["llm"]["agents"]) == set(manifest["agents"]["registry"])
    for agent_id, actor in resolved["llm"]["agents"].items():
        assert actor["role"] == manifest["agents"]["registry"][agent_id]["role"]


def test_bundle_references_resolve_for_source_and_staged_payload_roots(tmp_path):
    module = load_module()
    active_knowledge = module.load_vc_knowledge(BLUEPRINT_DIR)

    assert module.resolve_knowledge_dir(
        BLUEPRINT_DIR,
        active_knowledge,
        "@/payloads/knowledge",
    ) == (BLUEPRINT_DIR / "payloads" / "knowledge").resolve()

    staged_root = tmp_path / "attempt"
    staged_knowledge = staged_root / "knowledge"
    staged_knowledge.mkdir(parents=True)
    assert module.resolve_knowledge_dir(
        staged_root,
        active_knowledge,
        "@/payloads/knowledge",
    ) == staged_knowledge.resolve()


def test_step_definitions_resolve_to_direct_agent_handlers():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    registry = manifest["agents"]["registry"]
    assigned = set()
    for step in manifest["workflow"]["steps"]:
        module = importlib.import_module(step["run"]["definition"])
        stack = [module.STEP.to_dict()["flow"]]
        while stack:
            item = stack.pop()
            if item["type"] == "agent":
                assigned.add(item["agent_id"])
            else:
                stack.extend(item.get("items") or [])
    handlers = {registry[agent_id]["handler"] for agent_id in assigned}

    assert assigned == set(registry)
    assert "agents.public_researcher" in handlers
    scorer_handlers = {
        f"agents.{agent_id}"
        for agent_id in registry
        if agent_id.endswith("_scorer")
    }
    assert scorer_handlers <= handlers
    assert not any(handler.startswith("steps.") for handler in handlers)
    assert all(":" not in handler for handler in handlers)

    evidence = importlib.import_module("steps.prepare_company_evidence").STEP.to_dict()
    assert [item["agent_id"] for item in evidence["flow"]["items"]] == [
        "document_evidence_extractor",
        "claim_normalizer",
    ]
    assert all(callable(resolve_handler(handler)) for handler in handlers)


def test_manifest_compiles_step_boundaries_parallel_joins_and_unique_invocations():
    expanded = expand_manifest_source(
        json.loads((BLUEPRINT_DIR / "manifest.json").read_text()),
        root_dir=BLUEPRINT_DIR,
    )
    nodes = {node["node_id"]: node for node in expanded["agents"]["nodes"]}
    steps = {step["id"]: step for step in expanded["workflow"]["steps"]}

    assert nodes["prepare_company_evidence__start"]["agent_type"] == "step_source"
    assert nodes["prepare_company_evidence__end"]["agent_type"] == "step_sink"
    assert nodes["collect_public_research__join_2"]["agent_type"] == "step_join"
    assert len(nodes["collect_public_research__join_2"]["config"]["expected_sources"]) == 5
    assert len(nodes["calculate_valuation_scores__join_2"]["config"]["expected_sources"]) == 7
    assert steps["collect_public_research"]["agent_ids"][1:6] == [
        "collect_public_research__company_identity_researcher",
        "collect_public_research__funding_researcher",
        "collect_public_research__market_comp_researcher",
        "collect_public_research__traction_verifier",
        "collect_public_research__rendered_page_researcher",
    ]
    assert steps["collect_public_research"]["start_agent_id"] == "collect_public_research__start"
    assert steps["collect_public_research"]["end_agent_id"] == "collect_public_research__end"
    assert {"source": "domain", "target": "domain"} in nodes[
        "detect_packet_changes__startup_folder_watcher"
    ]["config"]["upload_paths"]


def test_runtime_module_resolves_the_blueprint_root_after_the_entrypoint_move():
    runner = load_module()
    layout = BlueprintBundleLayout.discover(RUNTIME_PATH)

    assert layout.root == BLUEPRINT_DIR
    assert layout.payload_root == BLUEPRINT_DIR / "payloads"
    assert (
        default_config_path(RUNTIME_PATH) == BLUEPRINT_DIR / "config" / "default.json"
    )
    assert runner.PROMPTS.prompt_dir == BLUEPRINT_DIR / "payloads" / "prompts"


def test_runtime_context_uses_the_platform_staged_input_folder(tmp_path):
    from domain.runtime_services import runtime_context_for_step

    staged_inputs = tmp_path / "staged-inputs"
    staged_inputs.mkdir()
    (staged_inputs / "packet.txt").write_text("Company: Staged Input", encoding="utf-8")
    output_folder = tmp_path / "outputs"
    run_id = "staged-input-run"

    context = runtime_context_for_step(
        inputs={
            "document_folder": None,
            "input_folder": str(staged_inputs),
            "output_folder": str(output_folder),
        },
        runs_root=tmp_path / "runs",
        run_id=run_id,
    )

    assert context["document_folder"] == staged_inputs
    assert context["payload"]["document_folder"] == str(staged_inputs)
    assert context["payload"]["input_folder"] == str(staged_inputs)

    persisted = json.loads(
        (tmp_path / "runs" / run_id / "workflow_state" / "runtime_context.json").read_text()
    )
    assert persisted["document_folder"] == str(staged_inputs)

    replay = runtime_context_for_step(
        inputs={"document_folder": None, "output_folder": str(output_folder)},
        runs_root=tmp_path / "runs",
        run_id=run_id,
    )
    assert replay["document_folder"] == staged_inputs


def test_vc_has_no_local_blueprint_entrypoint_or_generic_dispatch():
    runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")

    assert not (RUNTIME_PATH.parent / "run_blueprint.py").exists()
    assert "def run_blueprint(" not in runtime_source
    assert "def execute_runtime_handler(" not in runtime_source
    assert len(runtime_source.splitlines()) <= 500
    assert "globals().update(" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in (BLUEPRINT_DIR / "payloads" / "agents").glob("*.py")
    )


def test_runtime_boundary_contains_only_runtime_preparation_responsibilities():
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    function_names = {
        node.name
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert function_names <= {
        "runtime_context_for_step",
        "agentic_research_config",
        "step_agent_review_selected",
        "build_runtime_services",
        "persist_action_budget_state",
        "append_event",
        "append_debug_record",
        "write_benchmark_artifacts",
    }
    for path in (PAYLOAD_DIR / "agents").glob("*.py"):
        if path.name == "_shared.py":
            continue
        agent_source = path.read_text(encoding="utf-8")
        assert "from runtime.runtime import" not in agent_source
        assert "from runtime import runtime" not in agent_source
        assert "agents.domain" not in agent_source

    assert not (PAYLOAD_DIR / "agents" / "domain.py").exists()
    assert not (PAYLOAD_DIR / "runtime" / "dependencies.py").exists()
    assert "from agents" not in source
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) <= 800
        for path in (PAYLOAD_DIR / "domain").rglob("*.py")
    )


def test_old_stage_routers_and_in_process_crew_modules_are_removed():
    removed = {
        "steps/intake.py",
        "steps/evidence.py",
        "steps/research.py",
        "steps/scoring.py",
        "steps/reporting.py",
        "agents/public_research_crew.py",
        "agents/valuation_scoring_crew.py",
        "agents/domain.py",
    }

    assert all(not (PAYLOAD_DIR / relative).exists() for relative in removed)


def test_agent_invocation_replay_uses_durable_idempotency_record(tmp_path):
    from agents._shared import create_agent_handler

    calls = []

    def domain_handler(ctx, **_options):
        calls.append(ctx["idempotency_key"])
        return {"value": len(calls)}

    handler = create_agent_handler(domain_handler)
    context = StepContext(
        step_id="test_step",
        agent_id="test_agent",
        invocation_id="test_step__test_agent",
        run_id="replay-run",
        idempotency_key="replay-run/test_step__test_agent",
        message={"body": {"step_input": {"kwargs": {"output_folder": str(tmp_path)}}}},
        config={
            "agentic_research": {"enabled": False},
            "actor_review": {"llm_actor_ids": []},
            "knowledge_rag": {"enabled": False, "required": False},
        },
    )

    first = handler(context, runs_root=tmp_path)
    replay = handler(context, runs_root=tmp_path)

    assert first.outputs == {"value": 1}
    assert replay.outputs == {"value": 1}
    assert calls == ["replay-run/test_step__test_agent"]
    assert (
        tmp_path
        / "replay-run"
        / "workflow_state"
        / "agent_invocations"
        / "test_step__test_agent.json"
    ).exists()


def test_model_contract_uses_the_shared_adaptive_default():
    llm = load_runtime_config(RUNTIME_PATH)["llm"]

    assert llm["model"] == "default"
    assert "model" not in llm["configs"]["primary"]
    assert "small_model_profile" not in llm
    assert "large_model_profile" not in llm


def test_valuation_methods_map_to_discoverable_specialist_agents():
    rb = load_module()
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    registry = manifest["agents"]["registry"]

    assert set(rb.SCORER_AGENT_BY_METHOD) == set(rb.METHOD_IDS)
    assert set(rb.METHOD_SCORER_FUNCTIONS) == set(rb.METHOD_IDS)
    assert set(rb.SCORER_AGENT_BY_METHOD.values()) <= set(rb.AGENT_IDS)
    for agent_id in rb.SCORER_AGENT_BY_METHOD.values():
        assert registry[agent_id]["handler"] == f"agents.{agent_id}"
        assert (PAYLOAD_DIR / "agents" / f"{agent_id}.py").exists()

    valuation_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PAYLOAD_DIR / "domain" / "valuation").glob("*.py")
    )
    assert "scorer_id=" not in valuation_source


def test_agent_lifecycle_exceptions_are_manifest_owned():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    batch_lifecycle = manifest["agents"]["registry"]["batch_index_writer"][
        "lifecycle"
    ]
    shared_source = (PAYLOAD_DIR / "agents" / "_shared.py").read_text(
        encoding="utf-8"
    )

    assert batch_lifecycle == {
        "rag_stage": "batch_indexing",
        "review_after_run": False,
    }
    assert 'agent_id == "batch_index_writer"' not in shared_source
    assert 'agent_id != "batch_index_writer"' not in shared_source


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


def test_research_prompts_include_agent_specific_rag_and_tool_policy():
    rb = load_module()
    plan = {
        "agent_queries": {"funding_researcher": ["Acme funding"]},
        "lanes": [],
        "signals": {},
        "privacy_policy": "public-safe",
    }
    rag_context = {
        "status": "ready",
        "context": "Funding playbook",
        "citations": [{"ref": 1}],
    }
    system_prompt, prompt = rb.build_research_agent_prompt(
        company="Acme",
        agent_id="funding_researcher",
        plan=plan,
        internet={},
        allowed_tools={"browser_search", "finish"},
        remaining_tool_calls=2,
        rag_context=rag_context,
        knowledge_rag={
            "enabled": True,
            "status": "ready",
            "config": {"required": True},
        },
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
        knowledge_rag={
            "enabled": True,
            "status": "ready",
            "config": {"required": False},
        },
    )[1]
    writer_prompt = rb.build_actor_review_prompt(
        actor_id="company_report_writer",
        actor_spec={"role": "Company Report Writer"},
        context=context,
        knowledge_rag={
            "enabled": True,
            "status": "ready",
            "config": {"required": False},
        },
    )[1]

    assert scorer_prompt["task"] != writer_prompt["task"]
    assert "berkus_method" in scorer_prompt["focus"]
    assert "evidence traceability" in writer_prompt["focus"]


def test_required_rag_zero_citations_fails_before_llm(monkeypatch):
    rb = load_module()
    calls = {"llm": 0}

    def fake_require_ready(
        state, *, stage="", company="", context=None, min_citations=0
    ):
        if min_citations and not (context or {}).get("citations"):
            raise RuntimeError("required RAG returned zero citations")
        return context if context is not None else state

    class SpyLLM:
        def generate_json(self, **kwargs):
            calls["llm"] += 1
            return {"tool_calls": [{"tool": "finish"}], "rag_refs": [1]}

    monkeypatch.setattr(rb, "skill_require_ready_knowledge_rag", fake_require_ready)
    monkeypatch.setattr(
        rb,
        "retrieve_knowledge_rag_context",
        lambda **kwargs: {
            "enabled": True,
            "status": "ready",
            "context": "",
            "citations": [],
            "chunks": [],
        },
    )

    with pytest.raises(RuntimeError, match="zero citations"):
        rb.run_agentic_research_agent(
            company="Acme",
            agent_id="funding_researcher",
            plan={
                "agent_queries": {"funding_researcher": ["Acme funding"]},
                "queries": ["Acme"],
                "lanes": [],
            },
            internet={},
            run_dir=None,
            action_budget=None,
            llm=SpyLLM(),
            agentic={
                "allowed_tools": ["finish"],
                "max_iterations_per_agent": 1,
                "max_tool_calls_per_agent": 1,
            },
            trace=[],
            knowledge_rag={
                "enabled": True,
                "status": "ready",
                "config": {"required": True},
            },
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


def test_runtime_rag_uses_a_stable_database_per_agent(monkeypatch):
    rb = load_module()
    config = {
        "knowledge_rag": {
            "enabled": True,
            "namespace": "vc_runtime",
            "db_root": "/runtime/rag",
            "db_path": "vc.db",
        }
    }

    funding = rb.with_agent_scoped_knowledge_rag_config(
        config, agent_id="funding_researcher"
    )
    market = rb.with_agent_scoped_knowledge_rag_config(
        config, agent_id="market_comp_researcher"
    )

    assert funding["knowledge_rag"]["namespace"] == (
        "vc_runtime_vc_assistant_funding_researcher"
    )
    assert market["knowledge_rag"]["namespace"] == (
        "vc_runtime_vc_assistant_market_comp_researcher"
    )
    assert funding["knowledge_rag"]["db_path"] == "vc_funding_researcher.db"
    assert market["knowledge_rag"]["db_path"] == "vc_market_comp_researcher.db"
    assert config["knowledge_rag"]["namespace"] == "vc_runtime"
    assert config["knowledge_rag"]["db_path"] == "vc.db"


def test_agentic_rag_query_prioritizes_agent_playbook_terms(monkeypatch):
    rb = load_module()
    captured: dict[str, str] = {}

    def fake_require_ready(
        state, *, stage="", company="", context=None, min_citations=0
    ):
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
            return {
                "tool_calls": [{"tool": "finish", "reason": "agent guidance reviewed"}],
                "rag_refs": [1],
            }

    monkeypatch.setattr(rb, "skill_require_ready_knowledge_rag", fake_require_ready)
    monkeypatch.setattr(rb, "retrieve_knowledge_rag_context", fake_retrieve)

    rb.run_agentic_research_agent(
        company="Aurora Ai",
        agent_id="research_planner",
        plan={
            "agent_queries": {
                "research_planner": [
                    "Aurora Ai company website Crunchbase public profile"
                ]
            },
            "queries": ["Aurora Ai startup public evidence"],
            "lanes": [{"lane_id": "fundraising"}],
        },
        internet={},
        run_dir=None,
        action_budget=None,
        llm=FinishLLM(),
        agentic={
            "allowed_tools": ["finish"],
            "max_iterations_per_agent": 1,
            "max_tool_calls_per_agent": 1,
        },
        trace=[],
        knowledge_rag={
            "enabled": True,
            "status": "ready",
            "config": {"required": True},
        },
    )

    assert "VC diligence lane planning" in captured["query"]
    assert "public-safe startup research" in captured["query"]
    assert "fundraising" in captured["query"]
    assert not captured["query"].startswith("Aurora Ai")


def test_funding_researcher_uses_agentic_path(monkeypatch):
    rb = load_module()
    called: list[str] = []

    def fake_agentic(**kwargs):
        called.append(kwargs["agent_id"])
        return kwargs["agent_id"], []

    monkeypatch.setattr(rb, "run_agentic_research_agent", fake_agentic)
    monkeypatch.setattr(
        rb,
        "_run_research_agent",
        lambda company, agent_id, query, plan, internet, run_dir, action_budget: (
            agent_id,
            [],
        ),
    )

    rb.research_company_with_agents(
        "Acme",
        {
            "internet_research": {"enabled": True, "max_parallel_research_agents": 1},
            "agentic_research": {"enabled": True, "agent_ids": ["funding_researcher"]},
        },
        llm=object(),
    )

    assert called == ["funding_researcher"]


def test_agentic_agent_gap_fill_runs_deterministic_research(monkeypatch):
    rb = load_module()
    deterministic_calls: list[str] = []

    def fake_agentic(**kwargs):
        return kwargs["agent_id"], [
            rb._source_record(
                company=kwargs["company"],
                query="Acme funding",
                url="research_plan",
                title="planned",
                snippet="planned",
                status="planned",
                skill="research_planner",
                verification_target=kwargs["agent_id"],
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

    monkeypatch.setattr(rb, "run_agentic_research_agent", fake_agentic)
    monkeypatch.setattr(rb, "_run_research_agent", fake_one_stage)

    by_agent = rb.research_company_with_agents(
        "Acme",
        {
            "internet_research": {"enabled": True, "max_parallel_research_agents": 1},
            "agentic_research": {"enabled": True, "agent_ids": ["funding_researcher"]},
        },
        llm=object(),
    )

    assert deterministic_calls.count("funding_researcher") == 1
    assert any(
        source.get("fallback_after_agentic") is True
        for source in by_agent["funding_researcher"]
    )
    assert any(
        rb.is_substantive_public_source(source)
        for source in by_agent["funding_researcher"]
    )


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
    assert (
        summaries[0]["research_sources"]["source_quality_counts"]["public_confirmation"]
        == 1
    )
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
    assert (
        len(report["evidence"][0]["text_preview"])
        <= rb.MAX_TRANSPORT_TEXT_PREVIEW_CHARS + 20
    )
    assert report["research_sources"][0]["url"] == "https://acme.example/funding"
    assert (
        len(report["research_sources"][0]["snippet"])
        <= rb.MAX_TRANSPORT_SNIPPET_CHARS + 20
    )


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
        llm.generate_json(
            system_prompt="actor", user_prompt="{}", fallback={"actor_id": "actor"}
        )
