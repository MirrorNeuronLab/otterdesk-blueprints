from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_goal_work_packet_skill import (
    build_goal_work_packet,
    persist_goal_work_packet,
    publish_goal_work_packet,
    publish_goal_status,
    read_peer_goal_packets,
    summarize_peer_goal_packets,
)
from mn_sdk.blueprint_support.workflow_state import write_json

from .common import (
    ASPECT_ARTIFACT_ID,
    ASPECT_PACKET_PATH,
    BLUEPRINT_ID,
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
    settings = (context.get("config") or {}).get("mcp_collaboration") or {}
    exchange = publish_goal_work_packet(
        run_dir=context["run_dir"],
        packet=packet,
        job_id=str(context.get("job_id") or context.get("run_id") or "local-job"),
        blueprint_id=BLUEPRINT_ID,
        run_id=str(context.get("run_id") or ""),
        enabled=bool(settings.get("enabled", True) and settings.get("publish_local_exchange", True)),
    )
    return {
        "status": "completed",
        "work_packet": packet,
        "work_packet_artifact": artifact,
        "mcp_exchange": exchange,
    }


def publish_workflow_status(
    context: dict[str, Any],
    *,
    status: str,
    stage: str,
    summary: str,
    idempotency_key: str,
) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    settings = (context.get("config") or {}).get("mcp_collaboration") or {}
    return publish_goal_status(
        run_dir=context["run_dir"],
        job_id=str(context.get("job_id") or context.get("run_id") or "local-job"),
        blueprint_id=BLUEPRINT_ID,
        run_id=str(context.get("run_id") or ""),
        goal_id=str(inputs.get("goal_id") or DEFAULT_GOAL_ID),
        status=status,
        stage=stage,
        summary=summary,
        idempotency_key=idempotency_key,
        enabled=bool(
            settings.get("enabled", True)
            and settings.get("publish_local_exchange", True)
        ),
    )


def list_packets(context: dict[str, Any]) -> list[dict[str, Any]]:
    packets = context["state_store"].list_entity_objects("work_packets")
    return sorted(packets.values(), key=lambda item: (str(item.get("stage")), str(item.get("work_packet_id"))))


def peer_packets(context: dict[str, Any]) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    settings = (context.get("config") or {}).get("mcp_collaboration") or {}
    return read_peer_goal_packets(
        inputs.get("peer_mcp_servers") or [],
        goal_id=str(inputs.get("goal_id") or DEFAULT_GOAL_ID),
        enabled=bool(settings.get("peer_reads_enabled", False)),
        max_servers=int(settings.get("max_peer_servers", 8)),
        max_records_per_peer=int(settings.get("max_records_per_peer", 50)),
    )


def peer_signals(context: dict[str, Any]) -> dict[str, Any]:
    result = peer_packets(context)
    return {
        "status": result.get("status", "unknown"),
        "warnings": list(result.get("warnings") or []),
        "signals": summarize_peer_goal_packets(result, max_items=20),
    }


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
    peer_context: dict[str, Any],
    recommended_action_status: str = "awaiting_human_approval",
) -> dict[str, Any]:
    run_dir = Path(context["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    inputs = normalized_inputs(context)
    peer_signals = list(peer_context.get("signals") or [])
    peer_warnings = list(peer_context.get("warnings") or [])
    peer_workers = {
        str(signal.get("worker") or "")
        for signal in peer_signals
        if isinstance(signal, dict)
    }
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
        "collaboration": {
            "goal_work_packet": packet["work_packet_id"],
            "peer_input_mode": "explicit_mcp_servers_only",
            "mcp_exchange": "collaboration/mcp_exchange.sqlite3",
            "peer_read_status": peer_context.get("status", "unknown"),
            "peer_goal_packet_count": len(peer_signals),
            "peer_goal_signals": peer_signals,
            "peer_warnings": peer_warnings,
            "team_synthesis": {
                "shared_goal": packet["business_goal"],
                "operating_rule": "Use bounded peer evidence to resolve dependencies; never treat another role's recommendation as approval.",
                "signals_considered": len(peer_signals),
                "peer_workers_considered": sorted(worker for worker in peer_workers if worker),
                "handoffs_defined": len(cross_functional_handoffs),
                "unresolved_without_peer_evidence": [
                    handoff.get("needs_from")
                    for handoff in cross_functional_handoffs
                    if handoff.get("needs_from") and handoff.get("to") not in peer_workers
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
        "output_files": ["final_artifact.json", ASPECT_PACKET_PATH, "collaboration/mcp_exchange.sqlite3"],
    }
