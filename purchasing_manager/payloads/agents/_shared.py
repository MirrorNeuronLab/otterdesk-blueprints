"""Message-neutral binding for Purchasing Manager specialists."""

from __future__ import annotations

from typing import Any, Callable

from mn_prototype_stateful_step_agent import AgentHandlerOutput, MessageAgentSpec, StatefulStepContext, StatefulStepSpec, create_message_agent
from mn_sdk.blueprint_support import StepLifecycleHooks, source_manifest
from mn_sdk.step_runtime import AgentInput, artifact_reference, find_message_payload

from domain.common import purchase_llm
from domain.llm_analysis import llm_agent_selected
from domain.runtime_services import runtime_context_for_step


_manifest = source_manifest(__file__)
_contracts = _manifest.get("contracts") if isinstance(_manifest.get("contracts"), dict) else {}
_input_keys = frozenset(_contracts.get("inputs") or {})


def _prepare_agent_services(
    context: StatefulStepContext,
    *,
    llm_client: Any | None = None,
    **_options: Any,
) -> dict[str, Any]:
    mapping = context.to_mapping()
    agent_id = context.step_context.agent_id
    return {
        "llm": purchase_llm(mapping["config"], llm_client)
        if llm_agent_selected(mapping["config"], agent_id)
        else None
    }


_spec = StatefulStepSpec(
    context_factory=runtime_context_for_step,
    input_keys=_input_keys,
    prepare=_prepare_agent_services,
    hooks=StepLifecycleHooks(runtime_step_mode="agent_invocation"),
)


def create_domain_agent(agent_id: str, operation: Callable[..., dict[str, Any]]):
    def invoke(
        context: StatefulStepContext,
        *,
        agent_input: AgentInput,
        llm_client: Any | None = None,
        **options: Any,
    ) -> AgentHandlerOutput:
        prepared_llm = context.services.get("llm") if isinstance(context.services, dict) else None
        result = operation(
            context.to_mapping(), llm_client=prepared_llm or llm_client, **options
        )
        ref = artifact_reference("purchasing_manager_state", "workflow_state/purchasing_manager_state.json")
        artifacts = [ref]
        payload: dict[str, Any] = {
            "result": {
                key: value
                for key, value in result.items()
                if key not in {"final_artifact", "output_files"}
            },
            "state_artifact": ref,
        }
        if isinstance(result.get("final_artifact"), dict):
            final_ref = artifact_reference("final_artifact", "final_artifact.json")
            artifacts.append(final_ref)
            payload["final_artifact"] = final_ref
        return AgentHandlerOutput(
            payload=payload,
            artifacts=tuple(artifacts),
            metrics={"agent_id": agent_id},
        )

    return create_message_agent(MessageAgentSpec(stateful=_spec, input_resolver=lambda value: find_message_payload(value.payload, required_keys=_input_keys)), invoke)
