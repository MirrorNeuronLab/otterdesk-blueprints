"""VC runtime context and shared-service preparation only."""

from __future__ import annotations

from .common import *
from .intake import force_reprocess_enabled
from .knowledge import (
    load_vc_knowledge,
    prepare_knowledge_rag,
    require_ready_rag,
)
from .runtime_tools import BudgetedLLM, append_event, llm_requires_live, observed_operation

def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    base = create_blueprint_run_context(
        runtime_file=__file__,
        blueprint_id=BLUEPRINT_ID,
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    )
    blueprint_dir = base.layout.root
    resolved_config = base.config
    payload = base.payload
    output_folder = base.output_folder
    run_dir = base.run_dir
    persisted = read_json(workflow_state_file(run_dir, "runtime_context.json"))
    if persisted:
        payload.update(
            persisted.get("payload")
            if isinstance(persisted.get("payload"), dict)
            else {}
        )
        output_folder = expand_runtime_path(persisted.get("output_folder") or output_folder)
        run_dir = expand_runtime_path(persisted.get("run_dir") or run_dir)
        started_at = str(persisted.get("started_at") or base.started_at)
        force_reprocess = (
            bool(persisted["force_reprocess"])
            if "force_reprocess" in persisted
            else force_reprocess_enabled(payload, resolved_config)
        )
        monitoring = dict(payload.get("monitoring") or {})
        max_cycles = int(
            persisted.get("max_cycles") or monitoring.get("max_cycles") or 1
        )
    else:
        monitoring = dict(payload.get("monitoring") or {})
        max_cycles = int(monitoring.get("max_cycles") or 1)
        force_reprocess = force_reprocess_enabled(payload, resolved_config)
        started_at = base.started_at

    search_roots = [base.layout.payload_root, blueprint_dir, blueprint_dir.parent]
    document_folder = None
    first_candidate = None
    for raw_path in (
        persisted.get("document_folder") if persisted else None,
        payload.get("document_folder"),
        payload.get("input_folder"),
    ):
        if not str(raw_path or "").strip():
            continue
        candidate = resolve_existing_path(
            raw_path,
            search_roots,
            blueprint_id=BLUEPRINT_ID,
        )
        first_candidate = first_candidate or candidate
        if candidate.exists():
            document_folder = candidate
            break
    document_folder = (
        document_folder
        or first_candidate
        or base.layout.payload_root / "examples" / "sample_inputs"
    )
    payload["document_folder"] = str(document_folder)
    payload["input_folder"] = str(document_folder)
    context = base.to_mapping()
    context.update({
        "_base_context": base,
        "blueprint_dir": blueprint_dir,
        "output_folder": Path(output_folder),
        "run_dir": Path(run_dir),
        "document_folder": Path(document_folder),
        "max_cycles": max_cycles,
        "force_reprocess": force_reprocess,
        "started_at": started_at,
    })
    persist_runtime_context(context)
    return context

def persist_runtime_context(ctx: dict[str, Any]) -> None:
    persist_blueprint_run_context(
        ctx["_base_context"],
        document_folder=str(ctx["document_folder"]),
        max_cycles=ctx["max_cycles"],
        force_reprocess=bool(ctx["force_reprocess"]),
    )

def load_action_budget_state(ctx: dict[str, Any]) -> ActionBudget:
    budget = build_action_budget(ctx["config"])
    state = read_workflow_state(ctx["run_dir"], "action_ledger.json", {})
    if isinstance(state, dict) and "budget" in state:
        budget.budget = int(state.get("budget") or budget.budget)
        budget.used = int(state.get("used") or 0)
        actions = state.get("actions")
        budget.actions = [dict(item) for item in actions if isinstance(item, dict)] if isinstance(actions, list) else []
    return budget

def persist_action_budget_state(ctx: dict[str, Any], action_budget: ActionBudget) -> dict[str, Any]:
    summary = action_budget.summary(include_actions=True)
    write_workflow_state(ctx["run_dir"], "action_ledger.json", summary)
    return summary

def init_runtime_llm(ctx: dict[str, Any], action_budget: ActionBudget, llm_client: Any | None = None) -> tuple[Any, LlmCallLimiter]:
    limiter = build_llm_call_limiter(ctx["config"])
    require_live = llm_requires_live(ctx["config"])
    try:
        with observed_operation(ctx["run_dir"], phase="llm_init", operation="actor_llm.init"):
            llm = BudgetedLLM(
                get_actor_llm_client(ctx["config"], llm_client),
                action_budget,
                require_live=require_live,
                limiter=limiter,
                run_dir=ctx["run_dir"],
            )
            return llm, limiter
    except Exception as exc:
        append_event(ctx["run_dir"], "tool_call_failed", {"tool": "actor_llm.init", "status": "required_actor_llm_init_failed", "error": str(exc)})
        write_failed_run(ctx, exc)
        raise

def with_agent_scoped_knowledge_rag_config(
    config: dict[str, Any], *, agent_id: str = ""
) -> dict[str, Any]:
    """Give concurrently invoked agents independent Milvus Lite database files.

    Milvus Lite takes an exclusive lock on its database file. The VC workflow
    deliberately fans out specialist agents, so they cannot all open the
    blueprint-wide default file. A stable agent suffix retains each worker's
    unchanged-index cache while preventing cross-worker lock contention.
    """
    if not isinstance(config, dict) or not str(agent_id or "").strip():
        return config

    raw = config.get("knowledge_rag")
    if not isinstance(raw, dict) or raw.get("enabled") is False:
        return config

    base_namespace = str(
        raw.get("namespace")
        or os.environ.get("MN_RAG_NAMESPACE")
        or "mirror_neuron_rag"
    ).strip()
    scoped = {
        **raw,
        "namespace": f"{base_namespace}_{BLUEPRINT_ID}_{agent_id}",
    }
    if raw.get("db_path"):
        configured_path = Path(str(raw["db_path"]))
        suffix = configured_path.suffix or ".db"
        scoped["db_path"] = str(
            configured_path.with_name(
                f"{configured_path.stem}_{agent_id}{suffix}"
            )
        )

    return {**config, "knowledge_rag": scoped}


def prepare_runtime_knowledge_rag(ctx: dict[str, Any], *, stage: str) -> tuple[dict[str, Any], dict[str, Any]]:
    active_knowledge = load_vc_knowledge(ctx["blueprint_dir"])
    rag_config = with_agent_scoped_knowledge_rag_config(
        ctx["config"], agent_id=str(ctx.get("agent_id") or stage)
    )
    with observed_operation(
        ctx["run_dir"],
        phase="knowledge_rag",
        operation="prepare",
        embedding_provider=((rag_config.get("knowledge_rag") or {}).get("embedding_provider") if isinstance(rag_config.get("knowledge_rag"), dict) else ""),
        embedding_model=((rag_config.get("knowledge_rag") or {}).get("embedding_model") if isinstance(rag_config.get("knowledge_rag"), dict) else ""),
    ) as op:
        knowledge_rag = prepare_knowledge_rag(
            blueprint_dir=ctx["blueprint_dir"],
            resolved_config=rag_config,
            active_knowledge=active_knowledge,
            run_dir=ctx["run_dir"],
        )
        op.close(
            "completed",
            rag_status=knowledge_rag.get("status"),
            indexed_count=(knowledge_rag.get("index_summary") or {}).get("indexed_count") if isinstance(knowledge_rag.get("index_summary"), dict) else None,
        )
    try:
        require_ready_rag(knowledge_rag, stage=stage, run_dir=ctx["run_dir"])
    except Exception as exc:
        append_event(ctx["run_dir"], "tool_call_failed", {"tool": "knowledge_rag.index", "status": "required_rag_failed", "error": str(exc)})
        write_failed_run(ctx, exc)
        raise
    return active_knowledge, knowledge_rag

def build_runtime_services(
    ctx: dict[str, Any],
    *,
    llm_client: Any | None = None,
    need_llm: bool = False,
    rag_stage: str = "",
) -> dict[str, Any]:
    action_budget = load_action_budget_state(ctx)
    active_knowledge: dict[str, Any] = {}
    knowledge_rag: dict[str, Any] = {}
    if rag_stage:
        active_knowledge, knowledge_rag = prepare_runtime_knowledge_rag(ctx, stage=rag_stage)
    llm = None
    limiter = build_llm_call_limiter(ctx["config"])
    if need_llm:
        llm, limiter = init_runtime_llm(ctx, action_budget, llm_client)
    return {
        "action_budget": action_budget,
        "active_knowledge": active_knowledge,
        "knowledge_rag": knowledge_rag,
        "llm": llm,
        "llm_limiter": limiter,
    }
