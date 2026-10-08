"""Separate capture, person-detector and caption health for operator reads."""

import time
from datetime import datetime, timezone


def pipeline_status(person, captions, *, now=None):
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
