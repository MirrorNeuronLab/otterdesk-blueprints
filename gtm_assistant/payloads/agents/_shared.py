"""Route-neutral stateful binding for one business-role specialist."""

from __future__ import annotations

import time
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

from domain.common import ASPECT_ARTIFACT_ID, ASPECT_PACKET_PATH
from domain.collaboration import publish_workflow_status
from domain.runtime_services import runtime_context_for_step


_manifest = source_manifest(__file__)
_contracts = _manifest.get("contracts") if isinstance(_manifest.get("contracts"), dict) else {}
_input_keys = frozenset((_contracts.get("inputs") or {}).keys())
_spec = StatefulStepSpec(
    context_factory=runtime_context_for_step,
    input_keys=_input_keys,
    hooks=StepLifecycleHooks(runtime_step_mode="agent_invocation"),
)


def create_domain_agent(agent_id: str, operation: Callable[..., dict[str, Any]]):
    def invoke(
        context: StatefulStepContext,
        *,
        agent_input: AgentInput,
        **options: Any,
    ) -> AgentHandlerOutput:
        context_mapping = context.to_mapping()
        step_id = context.step_context.step_id
        invocation_id = context.step_context.invocation_id
        publish_workflow_status(
            context_mapping,
            status="working",
            stage=step_id,
            summary=f"Working on {step_id.replace('_', ' ')}.",
            idempotency_key=f"{invocation_id}:{step_id}:working",
        )
        try:
            result = operation(
                context_mapping,
                step_id=step_id,
                invocation_id=invocation_id,
                **options,
            )
        except Exception:
            publish_workflow_status(
                context_mapping,
                status="failed",
                stage=step_id,
                summary=f"{step_id.replace('_', ' ').capitalize()} needs attention.",
                idempotency_key=f"{invocation_id}:{step_id}:failed",
            )
            raise
        packet = result.get("work_packet") if isinstance(result.get("work_packet"), dict) else {}
        awaiting_review = bool(result.get("final_artifact") and packet.get("requested_approval"))
        publish_workflow_status(
            context_mapping,
            status="waiting_for_human" if awaiting_review else "completed",
            stage=step_id,
            summary=(
                f"Completed {step_id.replace('_', ' ')} and is waiting for review."
                if awaiting_review
                else f"Completed {step_id.replace('_', ' ')}."
            ),
            idempotency_key=f"{invocation_id}:{step_id}:{'waiting' if awaiting_review else 'completed'}",
        )
        if step_id.startswith("publish_") and result.get("final_artifact"):
            collaboration = (context_mapping.get("config") or {}).get(
                "mcp_collaboration"
            ) or {}
            grace_seconds = min(
                max(float(collaboration.get("chat_grace_seconds", 0)), 0.0),
                30.0,
            )
            if grace_seconds:
                time.sleep(grace_seconds)
        artifacts = []
        work_packet_artifact = result.get("work_packet_artifact")
        if isinstance(work_packet_artifact, str) and work_packet_artifact:
            artifacts.append(artifact_reference("business_goal_work_packet", work_packet_artifact))
        payload: dict[str, Any] = {
            "result": {
                key: value
                for key, value in result.items()
                if key not in {"final_artifact", "output_files"}
            }
        }
        if isinstance(result.get("final_artifact"), dict):
            final_ref = artifact_reference("final_artifact", "final_artifact.json")
            artifacts.extend([final_ref, artifact_reference(ASPECT_ARTIFACT_ID, ASPECT_PACKET_PATH)])
            payload["final_artifact"] = final_ref
        return AgentHandlerOutput(
            payload=payload,
            artifacts=tuple(artifacts),
            metrics={"agent_id": agent_id, "stage": context.step_context.step_id},
        )

    return create_message_agent(
        MessageAgentSpec(
            stateful=_spec,
            input_resolver=lambda value: find_message_payload(value.payload, required_keys=_input_keys),
        ),
        invoke,
    )
