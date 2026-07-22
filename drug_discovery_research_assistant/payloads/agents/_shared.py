"""Message-neutral bindings for drug-discovery specialists."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from mn_prototype_stateful_step_agent import AgentHandlerOutput, MessageAgentSpec, StatefulStepContext, StatefulStepSpec, create_message_agent
from mn_sdk.step_runtime import AgentInput, artifact_reference, find_message_payload

from domain.runtime_services import runtime_context_for_step


def _resolved_input_keys() -> frozenset[str]:
    raw_config = os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "")
    try:
        config = json.loads(raw_config)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Drug Discovery Research Assistant requires the resolved blueprint config"
        ) from exc

    interfaces = config.get("interfaces") if isinstance(config, dict) else None
    input_contract = (
        interfaces.get("input_contract")
        if isinstance(interfaces, dict)
        else None
    )
    if not isinstance(input_contract, dict) or not input_contract:
        raise RuntimeError(
            "Drug Discovery Research Assistant input contract is missing from resolved config"
        )
    return frozenset(str(key) for key in input_contract if str(key).strip())


_input_keys = _resolved_input_keys()
_spec = StatefulStepSpec(context_factory=runtime_context_for_step, input_keys=_input_keys)


def create_domain_agent(name: str, operation: Callable[..., dict[str, Any]]):
    def invoke(context: StatefulStepContext, *, agent_input: AgentInput, **options: Any) -> AgentHandlerOutput:
        result = operation(context.to_mapping(), **options)
        ref = artifact_reference("drug_discovery_state", "workflow_state/drug_discovery_state.json")
        artifacts = [ref]
        payload: dict[str, Any] = {"step_id": name, "state_artifact": ref}
        if isinstance(result.get("final_artifact"), dict):
            final_ref = artifact_reference("final_artifact", "final_artifact.json")
            artifacts.append(final_ref)
            payload["final_artifact"] = final_ref
        return AgentHandlerOutput(payload=payload, artifacts=tuple(artifacts), metrics={"step_id": name})

    return create_message_agent(MessageAgentSpec(stateful=_spec, input_resolver=lambda value: find_message_payload(value.payload, required_keys=_input_keys)), invoke)
