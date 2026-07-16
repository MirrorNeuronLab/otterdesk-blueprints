from __future__ import annotations

from typing import Any, Callable

from mn_prototype_stateful_step_agent import (
    AgentHandlerOutput,
    MessageAgentSpec,
    StatefulStepContext,
    StatefulStepSpec,
    create_message_agent,
)
from mn_sdk.blueprint_support import StepLifecycleHooks
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.step_runtime import (
    AgentInput,
    artifact_reference,
    find_message_payload,
    find_artifact_reference,
)

from runtime import runtime
from .review import review_agent_invocation


_MANIFEST = source_manifest(__file__)
_CONTRACTS = (
    _MANIFEST.get("contracts") if isinstance(_MANIFEST.get("contracts"), dict) else {}
)
_AGENT_REGISTRY = (
    (_MANIFEST.get("agents") or {}).get("registry")
    if isinstance(_MANIFEST.get("agents"), dict)
    else {}
)
_INPUT_CONTRACT = (
    _CONTRACTS.get("inputs")
    if isinstance(_CONTRACTS.get("inputs"), dict)
    else {}
)
_RUNTIME_INPUT_KEYS = frozenset(_INPUT_CONTRACT)


def _agent_lifecycle(agent_id: str) -> dict[str, Any]:
    registered = _AGENT_REGISTRY.get(agent_id)
    lifecycle = registered.get("lifecycle") if isinstance(registered, dict) else {}
    return lifecycle if isinstance(lifecycle, dict) else {}


def _prepare_agent_services(
    context: StatefulStepContext,
    *,
    llm_client: Any | None = None,
    **_options: Any,
) -> dict[str, Any]:
    mapping = context.to_mapping()
    agent_id = context.step_context.agent_id
    mapping["agent_id"] = agent_id
    agentic = runtime.agentic_research_config(mapping["config"])
    needs_agentic_llm = bool(agentic.get("enabled")) and agent_id in set(
        agentic.get("agent_ids") or []
    )
    needs_review_llm = runtime.step_agent_review_selected(mapping, [agent_id])
    needs_llm = needs_agentic_llm or needs_review_llm
    lifecycle = _agent_lifecycle(agent_id)
    rag_stage = str(lifecycle.get("rag_stage") or (agent_id if needs_llm else ""))
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
    domain_handler: Callable[..., Any],
) -> Callable[..., Any]:
    def invoke(
        context: StatefulStepContext,
        *,
        llm_client: Any | None = None,
        agent_input: AgentInput,
        **parameters: Any,
    ) -> Any:
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
        lifecycle = _agent_lifecycle(context.step_context.agent_id)
        if lifecycle.get("review_after_run", True) is not False:
            review_agent_invocation(
                mapping,
                step_id=context.step_context.step_id,
                agent_id=context.step_context.agent_id,
                services=context.services,
                llm_client=llm_client,
            )
        return result

    return create_message_agent(
        MessageAgentSpec(
            stateful=AGENT_SPEC,
            input_resolver=lambda value: _runtime_inputs(value.payload),
        ),
        invoke,
    )


def _runtime_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    step_input = (
        payload.get("step_input")
        if isinstance(payload.get("step_input"), dict)
        else payload
    )
    found = find_message_payload(step_input, required_keys=_RUNTIME_INPUT_KEYS)
    return found if found else {}


def durable_artifact(kind: str, path: str, **metadata: Any) -> dict[str, Any]:
    return artifact_reference(kind, path, **metadata)


def agent_output(
    payload: dict[str, Any],
    *artifacts: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    status: str = "completed",
) -> AgentHandlerOutput:
    return AgentHandlerOutput(
        payload=payload,
        artifacts=tuple(artifacts),
        metrics=dict(metrics or {}),
        status=status,
    )


def input_artifact(ctx: dict[str, Any], kind: str) -> dict[str, Any] | None:
    value = ctx.get("agent_input")
    return find_artifact_reference(value, kind) if isinstance(value, AgentInput) else None


__all__ = [
    "agent_output",
    "create_agent_handler",
    "durable_artifact",
    "input_artifact",
]
