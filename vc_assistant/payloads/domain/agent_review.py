"""Per-agent VC review selection and persistence composition."""

from __future__ import annotations

from .common import *
from .knowledge import (
    active_knowledge_reference,
    knowledge_rag_is_required,
    public_knowledge_rag_state,
    require_ready_rag,
    retrieve_knowledge_rag_context,
)
from .research_core import actor_review_config
from .review import not_llm_reviewed_actor_finding, run_vc_actor_reviews
from .runtime_services import (
    init_runtime_llm,
    load_action_budget_state,
    persist_action_budget_state,
    prepare_runtime_knowledge_rag,
)
from .runtime_tools import append_event, llm_requires_live, observed_operation

def step_agent_review_selected(ctx: dict[str, Any], agent_ids: list[str]) -> bool:
    selected = set(actor_review_config(ctx["config"]).get("llm_actor_ids") or [])
    return bool(selected & set(agent_ids))

def workflow_state_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    store = ctx.get("state_store") or WorkflowStateStore(ctx["run_dir"])
    company_records = store.read_object("company_records.json")
    queue = store.read_list("company_work_queue.json")
    analyses = store.list_entity_objects("analyses")
    return {
        "document_file_count": len(read_workflow_state(ctx["run_dir"], "document_files.json", []) or []),
        "company_record_count": len(company_records),
        "queued_company_count": len(queue),
        "analysis_count": len(analyses),
        "queued_statuses": sorted({str(item.get("status") or "") for item in queue}),
        "companies": sorted(company_records),
    }

def load_actor_findings_state(ctx: dict[str, Any]) -> dict[str, Any]:
    return read_workflow_state(ctx["run_dir"], "actor_findings.json", {}) or {}

def write_actor_findings_state(ctx: dict[str, Any], actor_findings: dict[str, Any]) -> None:
    write_workflow_state(ctx["run_dir"], "actor_findings.json", actor_findings)

def load_actor_review_warnings_state(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    value = read_workflow_state(ctx["run_dir"], "actor_review_warnings.json", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

def write_actor_review_warnings_state(ctx: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    write_workflow_state(ctx["run_dir"], "actor_review_warnings.json", warnings)

def _build_step_actor_review_context(
    ctx: dict[str, Any],
    *,
    step_id: str,
    agent_id: str,
    services: dict[str, Any],
    **_options: Any,
) -> dict[str, Any]:
    active_knowledge = services.get("active_knowledge") or {}
    knowledge_rag = services.get("knowledge_rag") or {}
    actor_rag_context = retrieve_knowledge_rag_context(
        knowledge_rag=knowledge_rag,
        query=f"{agent_id} {step_id} VC workflow quality evidence grounding scoring research report-only boundary",
        stage=agent_id,
        run_dir=ctx["run_dir"],
    )
    require_ready_rag(
        knowledge_rag,
        stage=agent_id,
        context=actor_rag_context,
        min_citations=1,
        run_dir=ctx["run_dir"],
    )
    prompt_rag_context = {
        key: value
        for key, value in dict(actor_rag_context).items()
        if key not in {"context", "chunks"}
    }
    prompt_rag_context["citation_count"] = len(prompt_rag_context.get("citations") or [])
    active_knowledge_prompt_ref = active_knowledge_reference(active_knowledge)
    active_knowledge_prompt_ref.pop("title", None)
    return {
        "blueprint_id": BLUEPRINT_ID,
        "workflow_step_id": step_id,
        "agent_id": agent_id,
        "output_type": OUTPUT_TYPE,
        "report_only": True,
        "decision_boundary": "reports include scores, assumptions, evidence, and warnings only; users make all investment decisions",
        "state_summary": workflow_state_summary(ctx),
        "active_knowledge": active_knowledge_prompt_ref,
        "knowledge_rag": public_knowledge_rag_state(knowledge_rag),
        "rag_context": prompt_rag_context,
        "privacy_controls": {
            "public_research_queries": "company names, domains, categories, and non-confidential public claims only",
            "local_document_text": "not included in actor-review context",
        },
        "memory_boundary": {
            "rag_knowledge": "persistent Redis-backed knowledge index",
            "working_memory": "transient local prompt context; not written to Redis",
        },
    }

def _run_step_actor_review_agent(
    *,
    config: dict[str, Any],
    llm: Any,
    actor_ids: list[str],
    context: dict[str, Any],
    step_context: dict[str, Any],
    services: dict[str, Any],
    **_options: Any,
) -> dict[str, Any]:
    try:
        return run_vc_actor_reviews(
            config=config,
            llm=llm,
            actor_ids=actor_ids,
            state={"actor_findings": load_actor_findings_state(step_context)},
            context=context,
            knowledge_rag=services.get("knowledge_rag") or {},
            event_sink=step_context["run_dir"],
        )
    except Exception as exc:
        if llm_requires_live(config) or knowledge_rag_is_required(services.get("knowledge_rag") or {}):
            append_event(
                step_context["run_dir"],
                "tool_call_failed",
                {
                    "tool": "actor_llm",
                    "status": "required_actor_review_failed",
                    "agent_id": actor_ids[0] if actor_ids else "",
                    "error": str(exc),
                },
            )
            write_failed_run(step_context, exc)
        raise

def _recover_step_actor_review(
    ctx: dict[str, Any],
    error: Exception,
    *,
    actor_ids: list[str],
    **_options: Any,
) -> ActorReviewResult:
    actor_findings = load_actor_findings_state(ctx)
    actor_findings.update(
        actor_review_unavailable_findings(
            actor_ids,
            error,
            summary="Actor review unavailable; deterministic VC report artifacts were preserved.",
            finding_message="LLM actor review failed after deterministic reports were generated.",
        )
    )
    warning = {
        "kind": "actor_review",
        "status": "actor_review_unavailable",
        "message": "One or more LLM actor reviews failed after deterministic reports were generated; report artifacts were preserved.",
        "error": str(error),
        "affected_actor_count": len(actor_ids),
    }
    append_event(
        ctx["run_dir"],
        "tool_call_failed",
        {
            "tool": "actor_llm",
            "status": "actor_review_unavailable",
            "agent_id": actor_ids[0] if actor_ids else "",
            "error": str(error),
        },
    )
    return ActorReviewResult(
        findings=actor_findings,
        warnings=(warning,),
        status="completed_with_warnings",
    )

def _persist_step_actor_review(
    ctx: dict[str, Any],
    result: ActorReviewResult,
    **_options: Any,
) -> None:
    write_actor_findings_state(ctx, dict(result.findings or {}))
    warnings = load_actor_review_warnings_state(ctx)
    warnings.extend(dict(warning) for warning in result.warnings)
    write_actor_review_warnings_state(ctx, warnings)

STEP_ACTOR_REVIEW_AGENT = create_actor_review(
    ActorReviewSpec(
        runner=_run_step_actor_review_agent,
        actor_ids=lambda _ctx, *, agent_id, **_options: [agent_id],
        build_context=_build_step_actor_review_context,
        persist=_persist_step_actor_review,
        failure_policy=lambda ctx, *, services, **_options: (
            "fail"
            if llm_requires_live(ctx["config"])
            or knowledge_rag_is_required(services.get("knowledge_rag") or {})
            else "warn"
        ),
        on_error=_recover_step_actor_review,
    )
)

def run_step_agent_reviews(
    ctx: dict[str, Any],
    step_id: str,
    agent_ids: list[str],
    services: dict[str, Any],
    *,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    selected = set(actor_review_config(ctx["config"]).get("llm_actor_ids") or [])
    review_agent_ids = [agent_id for agent_id in agent_ids if agent_id in selected]
    if not review_agent_ids:
        return {"reviewed_agent_ids": []}
    action_budget = services.get("action_budget") or load_action_budget_state(ctx)
    active_knowledge = services.get("active_knowledge") or {}
    knowledge_rag = services.get("knowledge_rag") or {}
    if not knowledge_rag:
        active_knowledge, knowledge_rag = prepare_runtime_knowledge_rag(ctx, stage=step_id)
    llm = services.get("llm")
    if llm is None:
        llm, limiter = init_runtime_llm(ctx, action_budget, llm_client)
        services["llm"] = llm
        services["llm_limiter"] = limiter
    services["active_knowledge"] = active_knowledge
    services["knowledge_rag"] = knowledge_rag
    for agent_id in review_agent_ids:
        STEP_ACTOR_REVIEW_AGENT(
            ctx,
            llm_client=llm,
            step_id=step_id,
            agent_id=agent_id,
            services=services,
            step_context=ctx,
        )
    persist_action_budget_state(ctx, action_budget)
    return {"reviewed_agent_ids": review_agent_ids}

def ensure_all_actor_findings(ctx: dict[str, Any]) -> dict[str, Any]:
    actor_specs = resolve_actor_specs(ctx["config"])
    actor_findings = load_actor_findings_state(ctx)
    for actor_id in AGENT_IDS:
        if actor_id not in actor_findings:
            actor_findings[actor_id] = not_llm_reviewed_actor_finding(actor_id, dict(actor_specs.get(actor_id) or {}))
    write_actor_findings_state(ctx, actor_findings)
    return actor_findings

def normalized_actor_review_warnings(ctx: dict[str, Any], actor_findings: dict[str, Any]) -> list[dict[str, Any]]:
    unavailable = [
        str(finding.get("error") or "")
        for finding in actor_findings.values()
        if isinstance(finding, dict) and finding.get("provider") == "actor_review_unavailable"
    ]
    if unavailable:
        return [
            {
                "kind": "actor_review",
                "status": "actor_review_unavailable",
                "message": "One or more LLM actor reviews failed after deterministic reports were generated; report artifacts were preserved.",
                "error": unavailable[0],
                "affected_actor_count": len(unavailable),
            }
        ]
    shared_warnings = shared_normalize_actor_review_warnings(actor_findings)
    return shared_warnings or load_actor_review_warnings_state(ctx)
