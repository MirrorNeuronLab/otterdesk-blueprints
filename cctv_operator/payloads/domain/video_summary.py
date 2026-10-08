"""On-demand, chronological aggregation of NVIDIA video captions.

Like VSS stream_summarize with LLM merging disabled, this reads already analyzed
intervals. Asking for a summary never starts capture or changes the watch goal.
"""

import json
from datetime import datetime, timezone


def _time(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("summary bounds require a timezone")
    return parsed.astimezone(timezone.utc)


def summarize_video(report, *, after="", before=""):
    lower, upper = _time(after) if after else None, _time(before) if before else None
    if lower and upper and lower > upper:
        raise ValueError("summary after must precede before")
    rows = []
    for row in report.get("observations") or []:
        if not isinstance(row, dict) or not row.get("observed_at"):
            continue
        timestamp = _time(row["observed_at"])
        if lower and timestamp < lower or upper and timestamp > upper:
            continue
        rows.append((timestamp, row))
    rows.sort(key=lambda item: item[0])
    events = []
    # Select whole captions, newest first, then restore chronology. Never
    # silently cut a caption or claim coverage of omitted observations.
    for _, row in reversed(rows[-50:]):
        event = {"start_time": row.get("capture_started_at") or row["observed_at"],
                 "end_time": row.get("capture_ended_at") or row["observed_at"],
                 "description": row.get("scene_understanding") or row.get("summary") or "",
                 "goal_matched": row.get("detected_target") is True,
                 "monitoring_goal": row.get("monitoring_goal"),
                 "frame_batch_ref": row.get("frame_batch_ref"),
                 "source_profile": row.get("source_profile"),
                 "risk_predictions": row.get("risk_predictions") or []}
        if len(json.dumps([event, *events]).encode()) > 3 * 1024:
            break
        events.insert(0, event)
    narrative = "\n".join(f"{e['start_time']} to {e['end_time']}: {e['description']}" for e in events)
    omitted = len(rows) - len(events)
    qualification = "Current-run sampled NVIDIA video analysis; capture times, not original recording time. Demo footage is recorded. Predictions are not observed events."
    summary = (f"{narrative}\n\n{qualification}" if events else "No analyzed video is available in this interval.")
    if omitted:
        summary += f" {omitted} observation(s) omitted from this bounded summary. Narrow the time interval for more detail."
    return {"schema_version": "mn.cctv.video_summary.v1", "summary": summary,
            "status": "ready" if events else "no_observations",
            "video_summary": narrative,
            "events": events, "observations_in_window": len(rows), "included_observations": len(events),
            "omitted_observations": omitted, "continuous_coverage": False,
            "qualification": qualification}
