"""Message-neutral binding for Legal Assistant specialist workers."""

from __future__ import annotations

from typing import Any, Callable

from mn_prototype_stateful_step_agent import AgentHandlerOutput, MessageAgentSpec, StatefulStepContext, StatefulStepSpec, create_message_agent
from mn_sdk.blueprint_support import StepLifecycleHooks, source_manifest
from mn_sdk.step_runtime import AgentInput, artifact_reference, find_message_payload

from legal_domain import workflow
from legal_domain.runtime_services import runtime_context_for_step


_manifest = source_manifest(__file__)
_contracts = _manifest.get("contracts") if isinstance(_manifest.get("contracts"), dict) else {}
_input_keys = frozenset(_contracts.get("inputs") or {})
_spec = StatefulStepSpec(
    context_factory=runtime_context_for_step,
    input_keys=_input_keys,
    hooks=StepLifecycleHooks(append_event=workflow.append_event, runtime_step_mode="agent_invocation"),
)


def create_domain_agent(name: str, operation: Callable[..., dict[str, Any]]):
    def invoke(context: StatefulStepContext, *, agent_input: AgentInput, **options: Any) -> AgentHandlerOutput:
        result = operation(context.to_mapping(), **options)
        ref = artifact_reference("legal_workflow_state", "workflow_state/legal_workflow_state.json")
        artifacts = [ref]
        payload: dict[str, Any] = {"step_id": name, "state_artifact": ref}
        if isinstance(result.get("final_artifact"), dict):
            final_ref = artifact_reference("final_artifact", "final_artifact.json")
            artifacts.append(final_ref)
            payload["final_artifact"] = final_ref
        return AgentHandlerOutput(payload=payload, artifacts=tuple(artifacts), metrics={"step_id": name})

    return create_message_agent(
        MessageAgentSpec(
            stateful=_spec,
            input_resolver=lambda value: find_message_payload(value.payload, required_keys=_input_keys),
        ),
        invoke,
    )
