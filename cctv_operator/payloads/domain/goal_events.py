"""Bind a model goal match to its actual sampled interval and evidence frame."""

from datetime import datetime, timezone


def goal_event(result, batch):
    if result.get("detected_target") is not True:
        return None
    value = result.get("goal_event")
    if not isinstance(value, dict):
        raise ValueError("a goal match requires goal_event frame indices")
    rows = batch["selected_frames"]
    indices = [value.get(key) for key in ("start_frame", "end_frame", "evidence_frame")]
    if any(type(index) is not int or not 1 <= index <= len(rows) for index in indices):
        raise ValueError("goal_event indices must name selected frames, starting at one")
    start, end, evidence = indices
    if not start <= evidence <= end:
        raise ValueError("goal_event evidence must lie within its observed interval")

    def timestamp(index):
        return datetime.fromtimestamp(rows[index - 1]["timestamp"], timezone.utc).isoformat().replace("+00:00", "Z")

    return {"start_frame": start, "end_frame": end, "evidence_frame": evidence,
            "started_at": timestamp(start), "ended_at": timestamp(end),
            "observed_at": timestamp(evidence), "frame_path": rows[evidence - 1]["path"],
            "timestamp_basis": batch.get("timestamp_basis", "worker_capture_unix_seconds")}
