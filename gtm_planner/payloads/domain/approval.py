"""Human decisions come exclusively from Core, never from files or peers."""
import time
from mn_sdk.human_interactions import publish_human_interaction_event, read_interaction_events


def approval(context, key, preview, *, expires_at):
    if len(preview) > 7800:
        raise ValueError("Review preview exceeds the visible approval limit")
    if time.time() * 1000 >= expires_at:
        return "expired"
    events = read_interaction_events(context["run_id"])
    matching = [e for e in events if e.get("payload", {}).get("request_id") == key]
    for event in reversed(matching):
        if event["type"] == "human_input_received":
            return "approved" if event["payload"].get("decision") == "approve" else "rejected"
        if event["type"] == "human_input_timeout":
            return "expired"
    if time.time() * 1000 >= expires_at:
        return "expired"
    if not matching:
        publish_human_interaction_event(context["run_id"], "human_input_requested", {
            "request_id": key, "interaction_kind": "approval", "prompt": preview,
            "options": [{"id":"approve", "label":"Approve", "action":"approve"},
                        {"id":"reject", "label":"Reject", "action":"reject"}],
            "expires_at": expires_at, "blocking": False, "status": "pending",
        })
    return "pending"
