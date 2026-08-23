from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_goal_work_packet_skill import (
    build_goal_work_packet,
    persist_goal_work_packet,
)
from mn_sdk.blueprint_support.workflow_state import write_json

from .common import (
    ASPECT_ARTIFACT_ID,
    ASPECT_PACKET_PATH,
    BUSINESS_GOAL,
    DEFAULT_BUSINESS_NAME,
    DEFAULT_GOAL_ID,
    WORKER_ID,
    WORKER_ROLE,
)
from .inputs import normalized_inputs


def build_packet(context: dict[str, Any], **fields: Any) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    return build_goal_work_packet(
        goal_id=str(inputs.get("goal_id") or DEFAULT_GOAL_ID),
        business_goal=str(inputs.get("business_goal") or BUSINESS_GOAL),
        worker_id=WORKER_ID,
        worker_role=WORKER_ROLE,
        created_at=str(context.get("started_at") or "not_reported"),
        **fields,
    )


def persist_packet(context: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    artifact = persist_goal_work_packet(context["state_store"], packet)
    return {
        "status": "completed",
        "work_packet": packet,
        "work_packet_artifact": artifact,
    }


def list_packets(context: dict[str, Any]) -> list[dict[str, Any]]:
    packets = context["state_store"].list_entity_objects("work_packets")
    return sorted(packets.values(), key=lambda item: (str(item.get("stage")), str(item.get("work_packet_id"))))


def write_final_artifact(
    context: dict[str, Any],
    packet: dict[str, Any],
    *,
    artifact_type: str,
    executive_summary: str,
    evidence: dict[str, Any],
    next_steps: list[str],
    data_status: str,
    role_contribution: str,
    north_star_question: str,
    role_scorecard: list[dict[str, Any]],
    founder_decisions: list[dict[str, Any]],
    cross_functional_handoffs: list[dict[str, Any]],
    ninety_day_plan: list[dict[str, Any]],
    recommended_action_status: str = "awaiting_human_approval",
) -> dict[str, Any]:
    run_dir = Path(context["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    inputs = normalized_inputs(context)
    final_artifact = {
        "schema_version": "mn.business_success.role_brief.v1",
        "type": artifact_type,
        "business_name": str(inputs.get("business_name") or DEFAULT_BUSINESS_NAME),
        "business_goal": packet["business_goal"],
        "goal_id": packet["goal_id"],
        "planning_horizon_days": int(inputs["planning_horizon_days"]),
        "worker": WORKER_ID,
        "worker_role": WORKER_ROLE,
        "role_contribution": role_contribution,
        "north_star_question": north_star_question,
        "role_scorecard": role_scorecard,
        "founder_decisions": founder_decisions,
        "data_status": data_status,
        "executive_summary": executive_summary,
        "recommended_action": {
            "decision": recommended_action_status,
            "recommendation": packet["decision_or_recommendation"],
        },
        "confidence": packet["confidence"],
        "evidence": evidence,
        "approval_queue": packet["requested_approval"],
        "risks": packet["risks"],
        "next_steps": next_steps,
        "ninety_day_plan": ninety_day_plan,
        "cross_functional_handoffs": cross_functional_handoffs,
        "source_refs": packet["source_refs"],
        "job_context": {
            "goal_work_packet": packet["work_packet_id"],
            "goal_work_packet_artifact": f"workflow_state/work_packets/{packet['work_packet_id']}.json",
            "evidence_boundary": "Run results contain only the evidence and assumptions recorded by this co-worker; missing cross-functional evidence remains explicit.",
            "team_synthesis": {
                "shared_goal": packet["business_goal"],
                "operating_rule": "Treat each cross-functional handoff as requested evidence, never as approval or an observed fact.",
                "handoffs_defined": len(cross_functional_handoffs),
                "unresolved_evidence_requests": [
                    handoff.get("needs_from")
                    for handoff in cross_functional_handoffs
                    if handoff.get("needs_from")
                ],
            },
        },
    }
    write_json(run_dir / "final_artifact.json", final_artifact)
    write_json(run_dir / ASPECT_PACKET_PATH, final_artifact)
    return {
        "status": "completed",
        "final_artifact": final_artifact,
        "aspect_artifact_id": ASPECT_ARTIFACT_ID,
        "aspect_packet_path": ASPECT_PACKET_PATH,
        "output_files": ["final_artifact.json", ASPECT_PACKET_PATH],
    }
