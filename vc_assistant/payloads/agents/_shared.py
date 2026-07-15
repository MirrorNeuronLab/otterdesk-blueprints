from __future__ import annotations

from typing import Any, Callable

from mn_prototype_stateful_step_agent import (
    StatefulStepContext,
    StatefulStepSpec,
    create_agent,
)
from mn_sdk.blueprint_support import StepLifecycleHooks
from mn_sdk.step_runtime import (
    AgentInput,
    StepContext,
    find_message_payload,
    receive_input,
    send_output,
)

from . import domain as runtime
from .review import review_agent_invocation


_RUNTIME_INPUT_KEYS = frozenset(
    {
        "document_folder",
        "input_folder",
        "output_folder",
        "monitoring",
        "force_reprocess",
    }
)


def _prepare_agent_services(
    context: StatefulStepContext,
    *,
    llm_client: Any | None = None,
    **_options: Any,
) -> dict[str, Any]:
    mapping = context.to_mapping()
    agent_id = context.step_context.agent_id
    agentic = runtime.agentic_research_config(mapping["config"])
    needs_agentic_llm = bool(agentic.get("enabled")) and agent_id in set(
        agentic.get("agent_ids") or []
    )
    needs_review_llm = runtime.step_agent_review_selected(mapping, [agent_id])
    needs_llm = needs_agentic_llm or needs_review_llm
    rag_stage = (
        "batch_indexing"
        if agent_id == "batch_index_writer"
        else (agent_id if needs_llm else "")
    )
    return {
        "workflow_state": context.state_store,
        **runtime.build_runtime_services(
            mapping,
            llm_client=llm_client,
            need_llm=needs_llm,
            rag_stage=rag_stage,
        ),
    }


def _finalize_agent_services(
    context: StatefulStepContext,
    *,
    result: Any,
    error: BaseException | None,
    **_options: Any,
) -> None:
    services = context.services
    if services.get("action_budget") is not None:
        runtime.persist_action_budget_state(
            context.to_mapping(), services["action_budget"]
        )


AGENT_SPEC = StatefulStepSpec(
    context_factory=runtime.runtime_context_for_step,
    input_keys=_RUNTIME_INPUT_KEYS,
    prepare=_prepare_agent_services,
    finalize=_finalize_agent_services,
    hooks=StepLifecycleHooks(
        append_event=runtime.append_event,
        append_debug=runtime.append_debug_record,
        write_benchmark=runtime.write_benchmark_artifacts,
        runtime_step_mode="agent_invocation",
    ),
)


def create_agent_handler(
    domain_handler: Callable[..., dict[str, Any]],
) -> Callable[..., Any]:
    def invoke(
        context: StatefulStepContext,
        *,
        llm_client: Any | None = None,
        agent_input: AgentInput,
        **parameters: Any,
    ) -> dict[str, Any]:
        invocation_id = (
            context.step_context.invocation_id
            or f"{context.step_context.step_id}__{context.step_context.agent_id}"
        )
        marker_name = f"agent_invocations/{invocation_id}.json"
        cached = context.state_store.read(marker_name, {})
        if (
            agent_input.idempotency_key
            and isinstance(cached, dict)
            and cached.get("idempotency_key") == agent_input.idempotency_key
            and isinstance(cached.get("outputs"), dict)
        ):
            return dict(cached["outputs"])
        mapping = context.to_mapping()
        mapping.update(
            {
                "workflow_step_id": context.step_context.step_id,
                "agent_id": context.step_context.agent_id,
                "agent_input": agent_input,
                "idempotency_key": agent_input.idempotency_key,
            }
        )
        result = domain_handler(mapping, llm_client=llm_client, **parameters)
        if context.step_context.agent_id != "batch_index_writer":
            review_agent_invocation(
                mapping,
                step_id=context.step_context.step_id,
                agent_id=context.step_context.agent_id,
                services=context.services,
                llm_client=llm_client,
            )
        context.state_store.write(
            marker_name,
            {
                "agent_id": context.step_context.agent_id,
                "invocation_id": invocation_id,
                "idempotency_key": agent_input.idempotency_key,
                "outputs": result,
                "status": "completed",
            },
        )
        return result

    managed_handler = create_agent(AGENT_SPEC, invoke)

    def run(step_context: StepContext, **parameters: Any):
        agent_input = receive_input(step_context)
        result = managed_handler(
            step_context,
            inputs=_runtime_inputs(agent_input.payload),
            agent_input=agent_input,
            **parameters,
        )
        outputs = (
            result.get("outputs") if isinstance(result.get("outputs"), dict) else result
        )
        invocation_id = (
            step_context.invocation_id
            or f"{step_context.step_id}__{step_context.agent_id}"
        )
        artifacts = [
            {
                "kind": "agent_result",
                "path": f"workflow_state/{invocation_id}_result.json",
                "invocation_id": invocation_id,
            },
            {
                "kind": "agent_idempotency_record",
                "path": f"workflow_state/agent_invocations/{invocation_id}.json",
                "invocation_id": invocation_id,
            },
        ]
        return send_output(outputs, artifacts=artifacts)

    run.__name__ = "run"
    return run


def _runtime_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    step_input = (
        payload.get("step_input")
        if isinstance(payload.get("step_input"), dict)
        else payload
    )
    found = find_message_payload(step_input, required_keys=_RUNTIME_INPUT_KEYS)
    return found if found else {}


__all__ = ["create_agent_handler"]
