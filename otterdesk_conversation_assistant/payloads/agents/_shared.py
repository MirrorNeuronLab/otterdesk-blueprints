"""Stateful step binding for the bounded conversation domain worker."""

from __future__ import annotations

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

from domain.runtime_services import runtime_context_for_step


_manifest = source_manifest(__file__)
_contracts = _manifest.get("contracts") if isinstance(_manifest.get("contracts"), dict) else {}
_input_keys = frozenset((_contracts.get("inputs") or {}).keys())
_spec = StatefulStepSpec(
    context_factory=runtime_context_for_step,
    input_keys=_input_keys,
    hooks=StepLifecycleHooks(runtime_step_mode="agent_invocation"),
)


def domain_result_payload(result: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload: dict[str, Any] = {
        "result": {
            key: value
            for key, value in result.items()
            if key != "final_artifact"
        }
    }
    artifacts: list[dict[str, Any]] = []
    if isinstance(result.get("final_artifact"), dict):
        # The bounded reply is part of the step result contract as well as a
        # durable audit artifact. Keeping it inline lets API clients read the
        # answer without reaching into synchronized worker storage.
        payload["result"]["artifact"] = dict(result["final_artifact"])
        final_ref = artifact_reference("final_artifact", "final_artifact.json")
        artifacts.append(final_ref)
        payload["final_artifact"] = final_ref
    return payload, artifacts


def create_domain_agent(agent_id: str, operation: Callable[..., dict[str, Any]]):
    def invoke(
        context: StatefulStepContext,
        *,
        agent_input: AgentInput,
        **options: Any,
    ) -> AgentHandlerOutput:
        result = operation(
            context.to_mapping(),
            step_id=context.step_context.step_id,
            invocation_id=context.step_context.invocation_id,
            **options,
        )
        payload, artifacts = domain_result_payload(result)
        return AgentHandlerOutput(
            payload=payload,
            artifacts=tuple(artifacts),
            metrics={"agent_id": agent_id, "stage": context.step_context.step_id},
        )

    return create_message_agent(
        MessageAgentSpec(
            stateful=_spec,
            input_resolver=lambda value: find_message_payload(
                value.payload,
                required_keys=_input_keys,
            ),
        ),
        invoke,
    )
