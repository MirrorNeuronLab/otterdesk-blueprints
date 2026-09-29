"""Narrow adapters over the SDK exchange and authenticated runtime discovery."""
import json
from pathlib import Path
from mn_sdk import Client
from mn_sdk_collaboration.work_packets import build_goal_work_packet, publish_goal_work_packet
from mn_sdk_mcp import discover_mcp_job_servers, get_mcp_job_updates


def stable_identity(context):
    client = Client(timeout=15)
    try:
        run = json.loads(client.get_run(context["job_id"]))
    finally:
        client.channel.close()
    if run.get("run_id") != context["job_id"] or not run.get("job_id"):
        raise ValueError("Runtime execution identity mismatch")
    return run["job_id"]


def publish(context, packet_id, stage, analysis, summary):
    packet = build_goal_work_packet(goal_id=context["payload"]["goal_id"],
        business_goal=context["payload"].get("common_goal") or "Market Bibblio through relevant, human-approved email outreach.",
        worker_id=context["stable_job_id"], worker_role=context["blueprint_id"], stage=stage,
        objective=summary, trigger="service_cycle", sources=[], observed_facts=[],
        assumptions=[], analysis=analysis, recommendation=summary, confidence="medium",
        risks=["Human approval is required before any email is sent."], requested_approval=[],
        outputs=[], next_check="Next service cycle", publication_state="final", packet_id=packet_id,
        created_at=context["started_at"])
    result = publish_goal_work_packet(run_dir=context["run_dir"], packet=packet,
        job_id=context["stable_job_id"], blueprint_id=context["blueprint_id"], run_id=context["run_id"])
    if result["status"] != "published":
        raise RuntimeError("Could not publish marketing collaboration packet")


def peer_updates(context, cursor):
    peer = context["payload"].get("peer_job_id")
    goal = context["payload"]["goal_id"]
    if not peer or peer == context["stable_job_id"]:
        raise ValueError("Configure the other co-worker's stable Job identity")
    client = Client(timeout=15)
    try:
        found = discover_mcp_job_servers(runtime_client=client, goal_id=goal, timeout_seconds=15)
        if found["status"] != "ok":
            raise RuntimeError("Marketing partner discovery unavailable")
        candidates = []
        for server in found["servers"]:
            # Registry job_id is execution-scoped. Resolve it through Core before contacting MCP.
            run = json.loads(client.get_run(server["job_id"]))
            if run.get("job_id") == peer:
                candidates.append(server)
    finally:
        client.channel.close()
    if not candidates:
        return [], cursor, "waiting_for_peer"
    if len(candidates) != 1:
        raise ValueError("More than one active marketing partner service")
    server = candidates[0]
    execution = server["job_id"]
    after = cursor.get("revision", 0) if cursor.get("execution") == execution else 0
    response = get_mcp_job_updates(server["config"], after_revision=after, kinds=["result"], include_staged=False, limit=100)
    if response.get("status") != "ok":
        raise RuntimeError("Marketing partner could not be read")
    data = response["updates"]
    expected = "gtm_executor" if context["blueprint_id"] == "gtm_planner" else "gtm_planner"
    identity = data.get("identity", {})
    if identity.get("job_id") != peer or identity.get("goal_id") != goal or identity.get("blueprint_id") != expected:
        raise ValueError("Marketing partner identity mismatch")
    packets = []
    for record in data.get("updates", []):
        packet = record.get("payload", {})
        if packet.get("goal_id") != goal or packet.get("worker") != peer or packet.get("worker_role") != expected:
            raise ValueError("Marketing packet identity mismatch")
        packets.append(packet)
    return packets, {"execution":execution, "revision":data["next_revision"]}, "connected"
