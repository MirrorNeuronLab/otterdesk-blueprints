"""Separate capture, person-detector and caption health for operator reads."""

import math
import time
from datetime import datetime, timezone


def pipeline_status(person, captions, *, now=None, last_presence=None):
    now = time.time() if now is None else now
    result = {"person_events": dict(person), "captions": dict(captions)}
    result["captions"]["sampler_status"] = person.get("captions", "starting")
    if person.get("person_detector") == "running" and now - float(person.get("last_person_frame_at") or 0) > 5:
        result["person_events"]["person_detector"] = "waiting_for_frames"
    warnings = []
    state = result["person_events"].get("person_detector")
    if state == "failed":
        warnings.append("Person detection stopped. Review worker logs and rebuild or restart.")
    elif state == "waiting_for_frames":
        warnings.append("Person detection is waiting for fresh video frames.")
    if captions.get("inflight_status") == "stalled":
        warnings.append("Caption processing stalled. Review the current run and restart after resolving the worker error.")
    if person.get("captions") == "failed":
        warnings.append("Caption sampling stopped. Review worker logs and rebuild or restart.")
    current = result["person_events"]
    count = current.get("visible_people")
    count = count if type(count) is int and count >= 0 else 0
    current["summary"] = {
        "failed": "Person detection stopped.",
        "waiting_for_frames": "Person detection is waiting for fresh video frames.",
        "ready": "Person detection is ready. Waiting for a video frame.",
    }.get(current.get("person_detector"), "Starting person detection…")
    if current.get("person_detector") == "running":
        current["summary"] = (f"{count} {'person' if count == 1 else 'people'} detected in the latest sampled frame."
                              if count else "No person detected in the latest sampled frame.")
    presence = last_presence or {}
    event = presence.get("person_event") or {}
    if presence.get("purpose") == "person_gate_only" and event.get("kind") == "person_presence_started":
        timestamp = event.get("confirmed_at")
        confirmed_count = event.get("person_count")
        if (type(timestamp) in (int, float) and math.isfinite(timestamp) and 0 < timestamp <= now
                and type(confirmed_count) is int and confirmed_count > 0):
            current["last_presence"] = {
                "observed_at": datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z"),
                "person_count": confirmed_count,
                "qualification": "Sampled person presence; not a verified monitoring-goal event.",
            }
    inflight = captions.get("inflight") or {}
    claimed_at = inflight.get("claimed_at")
    if type(claimed_at) in (int, float) and math.isfinite(claimed_at) and 0 < claimed_at <= now:
        elapsed = int(now - claimed_at)
        result["captions"]["summary"] = f"Scene analysis {'delayed' if elapsed > 300 else 'in progress'} ({elapsed} s)."
    else:
        result["captions"]["summary"] = "Waiting for the next scene sample."
    return result, " ".join(warnings)


def person_status_summary(pipeline):
    person = pipeline.get("person_events") or {}
    if person.get("person_detector") != "running":
        return ""
    timestamp = float(person["last_person_frame_at"])
    observed_at = datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")
    count = int(person.get("visible_people") or 0)
    finding = (f"RF-DETR detected {count} person(s) in the latest sampled frame." if count else
               "RF-DETR did not detect a person in the latest sampled frame. This does not establish continuous absence.")
    qualification = " Recorded demo playback." if person.get("source_profile") == "bundled_demo" else ""
    return f"{finding} Frame available at {observed_at}.{qualification}"
