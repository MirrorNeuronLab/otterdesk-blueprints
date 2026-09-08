"""Message-neutral binding for Financial Advisor specialist workers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mn_prototype_stateful_step_agent import (
    AgentHandlerOutput,
    MessageAgentSpec,
    StatefulStepContext,
    StatefulStepSpec,
    create_message_agent,
)
from mn_sdk.blueprint_support import StepLifecycleHooks, source_manifest
from mn_sdk.step_runtime import AgentInput, artifact_reference, find_message_payload

from domain import execution, runtime_services


_MANIFEST = source_manifest(__file__)
_CONTRACTS = _MANIFEST.get("contracts") if isinstance(_MANIFEST.get("contracts"), dict) else {}
_INPUT_CONTRACT = _CONTRACTS.get("inputs") if isinstance(_CONTRACTS.get("inputs"), dict) else {}
_INPUT_KEYS = frozenset(_INPUT_CONTRACT)


def _resolve_inputs(agent_input: AgentInput) -> dict[str, Any]:
    return find_message_payload(agent_input.payload, required_keys=_INPUT_KEYS)


_SPEC = StatefulStepSpec(
    context_factory=runtime_services.runtime_context_for_step,
    input_keys=_INPUT_KEYS,
    hooks=StepLifecycleHooks(
        append_event=runtime_services.append_event,
        runtime_step_mode="agent_invocation",
    ),
)


def create_domain_agent(agent_id: str, handler: Callable[[dict[str, Any]], dict[str, Any]]):
    """Bind one financial specialist to its durable domain operation."""

    def invoke(
        context: StatefulStepContext,
        *,
        agent_input: AgentInput,
        llm_client: Any | None = None,
        **_parameters: Any,
    ) -> AgentHandlerOutput:
        mapping = context.to_mapping()
        result = execution.execute_runtime_handler(
            agent_id,
            handler,
            inputs=dict(context.inputs),
            config=dict(context.config),
            # The generic run context intentionally stays free of domain state,
            # but the financial executor must receive its parent run root so
            # both layers address the exact same durable run directory.
            runs_root=Path(mapping["run_dir"]).parent,
            run_id=context.run_id,
            llm_client=llm_client,
        )
        step_ref = artifact_reference(
            "financial_agent_result",
            f"workflow_state/{agent_id}_result.json",
            owner=agent_id,
        )
        artifacts = [step_ref]
        payload: dict[str, Any] = {
            "status": str(result.get("status") or "completed"),
            "result_artifact": step_ref,
        }
        final_artifact = result.get("final_artifact")
        if isinstance(final_artifact, dict):
            final_ref = artifact_reference("final_artifact", "final_artifact.json")
            artifacts.append(final_ref)
            payload["final_artifact"] = final_ref
        return AgentHandlerOutput(
            payload=payload,
            artifacts=tuple(artifacts),
            metrics={"agent_id": agent_id},
        )

    return create_message_agent(
        MessageAgentSpec(stateful=_SPEC, input_resolver=_resolve_inputs), invoke
    )
