from __future__ import annotations

from typing import Any, Callable

from mn_prototype_actor_review_agent import wrap_agent
from mn_prototype_stateful_step_agent import StatefulStepContext, StatefulStepSpec, create_agent
from mn_sdk.blueprint_support import StepLifecycleHooks, complete_runtime_step, step_result

from runtime import runtime


def _prepare_step_services(
    context: StatefulStepContext,
    *,
    llm_client: Any | None = None,
    agent_ids: list[str] | None = None,
    **_options: Any,
) -> dict[str, Any]:
    mapping = context.to_mapping()
    step_id = context.step_context.step_id
    assigned_agents = [str(agent_id) for agent_id in (agent_ids or []) if str(agent_id)]
    agentic = runtime.agentic_research_config(mapping["config"])
    needs_agentic_llm = bool(agentic.get("enabled")) and bool(
        set(assigned_agents) & set(agentic.get("agent_ids") or [])
    )
    needs_review_llm = runtime.step_agent_review_selected(mapping, assigned_agents)
    needs_llm = needs_agentic_llm or needs_review_llm
    rag_stage = "batch_indexing" if "batch_index_writer" in assigned_agents else (step_id if needs_llm else "")
    return {
        "workflow_state": context.state_store,
        **runtime.build_runtime_services(
            mapping,
            llm_client=llm_client,
            need_llm=needs_llm,
            rag_stage=rag_stage,
        ),
    }


def _finalize_step_services(
    context: StatefulStepContext,
    *,
    result: Any,
    error: BaseException | None,
    llm_client: Any | None = None,
    **_options: Any,
) -> None:
    mapping = context.to_mapping()
    services = context.services
    if services.get("action_budget") is not None:
        runtime.persist_action_budget_state(mapping, services["action_budget"])


STEP_SPEC = StatefulStepSpec(
    context_factory=runtime.runtime_context_for_step,
    input_keys=frozenset(
        {
            "document_folder",
            "input_folder",
            "output_folder",
            "monitoring",
            "force_reprocess",
        }
    ),
    prepare=_prepare_step_services,
    finalize=_finalize_step_services,
    hooks=StepLifecycleHooks(
        append_event=runtime.append_event,
        append_debug=runtime.append_debug_record,
        write_benchmark=runtime.write_benchmark_artifacts,
    ),
)


def compose(handler: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def invoke(
        context: StatefulStepContext,
        *,
        llm_client: Any | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        mapping = context.to_mapping()
        mapping["workflow_step_id"] = context.step_context.step_id
        assigned_agents = [str(agent_id) for agent_id in options.pop("agent_ids", []) if str(agent_id)]
        result = handler(mapping, llm_client=llm_client, **options)
        payload = dict(result) if isinstance(result, dict) else {"result": result}
        payload.pop("workflow_step_id", None)
        complete_runtime_step(mapping, context.step_context.step_id, payload)
        return step_result(mapping, context.step_context.step_id, **payload)

    def review(
        context: StatefulStepContext,
        *,
        llm_client: Any | None = None,
        agent_ids: list[str] | None = None,
        **_options: Any,
    ) -> dict[str, Any]:
        return runtime.run_step_agent_reviews(
            context.to_mapping(),
            context.step_context.step_id,
            [str(agent_id) for agent_id in (agent_ids or []) if str(agent_id)],
            context.services,
            llm_client=llm_client,
        )

    reviewed = wrap_agent(
        invoke,
        review,
        when=lambda _context, *, agent_ids=None, **_options: "batch_index_writer" not in set(agent_ids or []),
    )
    return create_agent(STEP_SPEC, reviewed)
