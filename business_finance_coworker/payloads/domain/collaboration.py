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
    WORKER_ID,
    WORKER_ROLE,
)
from .inputs import normalized_inputs


def build_packet(context: dict[str, Any], **fields: Any) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    return build_goal_work_packet(
        goal_id=str(inputs.get("goal_id") or "bibblio-profitable-business"),
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
        goal_id=str(inputs.get("goal_id") or "bibblio-profitable-business"),
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
        goal_id=str(inputs.get("goal_id") or "bibblio-profitable-business"),
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
) -> dict[str, Any]:
    run_dir = Path(context["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    final_artifact = {
        "schema_version": "mn.bibblio.aspect_packet.v1",
        "type": artifact_type,
        "business_goal": packet["business_goal"],
        "goal_id": packet["goal_id"],
        "worker": WORKER_ID,
        "worker_role": WORKER_ROLE,
        "data_status": data_status,
        "executive_summary": executive_summary,
        "recommended_action": {
            "decision": "awaiting_human_approval",
            "recommendation": packet["decision_or_recommendation"],
        },
        "confidence": packet["confidence"],
        "evidence": evidence,
        "approval_queue": packet["requested_approval"],
        "risks": packet["risks"],
        "next_steps": next_steps,
        "source_refs": packet["source_refs"],
        "collaboration": {
            "goal_work_packet": packet["work_packet_id"],
            "peer_input_mode": "explicit_mcp_servers_only",
            "mcp_exchange": "collaboration/mcp_exchange.sqlite3",
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
