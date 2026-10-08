"""Narrow adapters over the SDK exchange and authenticated runtime discovery."""
from mn_sdk_collaboration.work_packets import build_goal_work_packet, publish_goal_work_packet
from mn_sdk.integrations.job_peers import read_group_work_packets, read_peer_work_packets, resolve_stable_job_id


def stable_identity(context):
    return resolve_stable_job_id(context["job_id"])


def publish(context, packet_id, stage, analysis, summary):
    peers = context["payload"].get("collaboration_peers", [])
    group_id = context["payload"].get("collaboration_group_id")
    group = {"group_id": group_id, "group_members": [context["stable_job_id"], *(peer["jobId"] for peer in peers)]} if group_id and peers else {}
    packet = build_goal_work_packet(goal_id=context["payload"]["goal_id"],
        business_goal=context["payload"].get("common_goal") or "Market Bibblio through relevant, human-approved email outreach.",
        worker_id=context["stable_job_id"], worker_role=context["blueprint_id"], stage=stage,
        objective=summary, trigger="service_cycle", sources=[], observed_facts=[],
        assumptions=[], analysis=analysis, recommendation=summary, confidence="medium",
        risks=["Human approval is required before any email is sent."], requested_approval=[],
        outputs=[], next_check="Next service cycle", publication_state="final", packet_id=packet_id,
        created_at=context["started_at"], **group)
    result = publish_goal_work_packet(run_dir=context["run_dir"], packet=packet,
        job_id=context["stable_job_id"], blueprint_id=context["blueprint_id"], run_id=context["run_id"])
    if result["status"] != "published":
        raise RuntimeError("Could not publish marketing collaboration packet")


def peer_updates(context, cursor):
    payload = context["payload"]
    group_id, peers = payload.get("collaboration_group_id"), payload.get("collaboration_peers", [])
    if group_id:
        if not isinstance(peers, list) or len(peers) > 4 or any(not isinstance(peer, dict) or peer.get("blueprintId") not in {"gtm_planner", "gtm_executor"} for peer in peers):
            raise ValueError("Unexpected marketing group role")
        if not peers:
            return [], {}, "waiting_for_peers"
        packets, updated, status = read_group_work_packets(peers=peers, own_job_id=context["stable_job_id"], group_id=group_id,
            goal_id=payload["goal_id"], cursors=cursor.get(group_id, {}))
        return packets, {group_id: updated}, status
    # Previously configured pairs retain their verified scalar-peer contract until edited.
    if not payload.get("peer_job_id"):
        return [], {}, "waiting_for_peer"
    expected = "gtm_executor" if context["blueprint_id"] == "gtm_planner" else "gtm_planner"
    return read_peer_work_packets(
        peer_job_id=context["payload"].get("peer_job_id"),
        own_job_id=context["stable_job_id"], goal_id=context["payload"]["goal_id"],
        expected_blueprint_id=expected, cursor=cursor,
    )
