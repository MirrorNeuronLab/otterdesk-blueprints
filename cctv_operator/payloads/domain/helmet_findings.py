"""Evidence required before the default missing-helmet condition can notify."""

from .detection_policy import DEFAULT_MONITORING_GOAL


def validate_helmet_goal(result, goal, batch):
    if goal != DEFAULT_MONITORING_GOAL or result.get("detected_target") is not True:
        return result
    event = result.get("goal_event") or {}
    frame = event.get("evidence_frame")
    confirmed = any(
        item.get("helmet_status") == "not_worn" and item.get("head_visible") is True
        and item.get("evidence_frame") == frame
        and type(frame) is int and 1 <= frame <= len(batch["selected_frames"])
        and bool(item.get("visible_evidence", "").strip())
        for item in result.get("helmet_observations", [])
    )
    if confirmed:
        return {**result, "goal_validation": "confirmed_missing_helmet"}
    # Preserve the scene account as uncertain history. A generic person claim
    # is insufficient evidence for this condition and must not become a notice.
    reason = "Missing helmet is unconfirmed: no visible uncovered head is bound to the event frame."
    return {**result, "detected": False, "detected_target": False, "detection_count": 0,
            "goal_event": None, "goal_validation": "missing_helmet_evidence_unavailable",
            "uncertainties": [*result.get("uncertainties", []), reason]}
