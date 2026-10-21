"""Bounded sampled-observation state and conversation projections."""

from typing import Any
from .visual_detection import compact_string, safe_confidence, safe_int

PERSON_TERMS = ("person", "people", "human", "worker", "visitor", "operator", "pedestrian")

def initial_state() -> dict[str, Any]:
    return {
        "frames_seen": 0,
        "source_mode": "stream",
        "last_alert_wall_ts": 0.0,
        "notified_goal": None,
        "last_human_notice_wall_ts": 0.0,
        "last_human_notice_signature": None,
        "detections": 0,
        "last_detection": None,
        "last_detection_report": None,
        "last_observation": None,
        "recent_observations": [],
        "attention_instruction": "",
        "attention_targets": [],
        "last_attention_update": None,
        "conversation_context": {
            "what_happened": "No video frames have been analyzed yet.",
            "attention_instruction": "",
            "recent_observations": [],
        },
        "last_error": None,
    }


def person_like_count(detection: dict[str, Any]) -> int:
    detections = detection.get("detections") if isinstance(detection.get("detections"), list) else []
    detection_people = 0
    for item in detections:
        if not isinstance(item, dict):
            continue
        text = " ".join(
            compact_string(item.get(key), limit=100).lower()
            for key in ("label", "category", "activity")
        )
        if any(term in text for term in PERSON_TERMS):
            detection_people += 1

    visible_subjects = detection.get("visible_subjects") if isinstance(detection.get("visible_subjects"), list) else []
    subject_people = sum(
        1
        for subject in visible_subjects
        if any(term in compact_string(subject, limit=100).lower() for term in PERSON_TERMS)
    )

    count = safe_int(detection.get("detection_count"), 0)
    text = " ".join(
        compact_string(detection.get(key), limit=500).lower()
        for key in ("summary", "detection_report", "activity_description")
    )
    inferred_people = count if count >= 2 and any(term in text for term in PERSON_TERMS) else 0
    return max(detection_people, subject_people, inferred_people)


def observation_from_detection(detection_payload: dict[str, Any]) -> dict[str, Any]:
    detected = bool(detection_payload.get("detected_target"))
    summary = compact_string(detection_payload.get("summary"), limit=500)
    report = compact_string(detection_payload.get("detection_report"), limit=900)
    activity = compact_string(detection_payload.get("activity_description"), limit=700)
    fallback = "No configured targets were observed in the monitored scene."
    return {
        "scene_understanding": detection_payload.get("scene_understanding"),
        "goal_event": detection_payload.get("goal_event"),
        "monitoring_goal": detection_payload.get("monitoring_goal"),
        "risk_predictions": detection_payload.get("risk_predictions"),
        "site_findings": detection_payload.get("site_findings", []),
        "site_context": detection_payload.get("site_context", {}),
        "site_coverage": detection_payload.get("site_coverage", {}),
        "uncertainties": detection_payload.get("uncertainties"),
        "capture_started_at": detection_payload.get("capture_started_at"),
        "capture_ended_at": detection_payload.get("capture_ended_at"),
        "frame_timestamps": detection_payload.get("frame_timestamps"),
        "timestamp_basis": detection_payload.get("timestamp_basis"),
        "source_profile": detection_payload.get("source_profile"),
        "analyzed_at": detection_payload.get("analyzed_at"),
        "frame_seq": detection_payload.get("frame_seq"),
        "camera_id": detection_payload.get("camera_id"),
        "video_position_seconds": detection_payload.get("video_position_seconds"),
        "source_mode": detection_payload.get("source_mode"),
        "source_uri": detection_payload.get("source_uri"),
        "source_name": detection_payload.get("source_name"),
        "source_index": detection_payload.get("source_index"),
        "source_count": detection_payload.get("source_count"),
        "stream_id": detection_payload.get("stream_id"),
        "detected_target": detected,
        "detection_count": safe_int(detection_payload.get("detection_count"), 0),
        "confidence": safe_confidence(detection_payload.get("confidence")),
        "risk_level": compact_string(detection_payload.get("risk_level"), limit=40) or "low",
        "summary": summary or fallback,
        "detection_report": report,
        "activity_description": activity,
        "visible_subjects": detection_payload.get("visible_subjects") if isinstance(detection_payload.get("visible_subjects"), list) else [],
        "detections": detection_payload.get("detections") if isinstance(detection_payload.get("detections"), list) else [],
        "person_like_count": person_like_count(detection_payload),
        "attention_instruction": compact_string(detection_payload.get("attention_instruction"), limit=500),
        "instruction_revision": detection_payload.get("instruction_revision"),
        "sampling_trigger": detection_payload.get("sampling_trigger"),
        "frame_batch_ref": detection_payload.get("frame_batch_ref"),
        "batch_id": detection_payload.get("batch_id"),
        "candidate_count": detection_payload.get("candidate_count"),
        "selected_count": detection_payload.get("selected_count"),
        "command_id": detection_payload.get("command_id"),
        "model_latency_ms": detection_payload.get("model_latency_ms"),
        "condition_screening": detection_payload.get("condition_screening")
        if isinstance(detection_payload.get("condition_screening"), dict) else {},
        "sampling_metrics": detection_payload.get("sampling_metrics")
        if isinstance(detection_payload.get("sampling_metrics"), dict)
        else {},
        "observed_at": detection_payload.get("observed_at"),
        "configured_targets": detection_payload.get("configured_targets")
        if isinstance(detection_payload.get("configured_targets"), list)
        else [],
        "matched_alert_targets": detection_payload.get(
            "matched_alert_targets"
        )
        if isinstance(detection_payload.get("matched_alert_targets"), list)
        else [],
        "alert_decision": detection_payload.get("alert_decision")
        if isinstance(detection_payload.get("alert_decision"), dict)
        else {},
    }


def what_happened_summary(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "No video frames have been analyzed yet."

    last = observations[-1]
    frame = last.get("frame_seq", "unknown")
    camera_id = last.get("camera_id") or "the monitored camera"
    if last.get("detected_target"):
        report = compact_string(last.get("detection_report"), limit=500) or compact_string(last.get("summary"), limit=500)
        activity = compact_string(last.get("activity_description"), limit=300)
        details = f" Activity: {activity}" if activity else ""
        return f"Most recently on frame {frame} from {camera_id}, {report}{details}"

    if last.get("scene_understanding"):
        return f"Most recently on frame {frame} from {camera_id}, {last['scene_understanding']}"
    previous_notable = next((item for item in reversed(observations[:-1]) if item.get("detected_target")), None)
    if previous_notable:
        notable_report = (
            compact_string(previous_notable.get("detection_report"), limit=400)
            or compact_string(previous_notable.get("summary"), limit=400)
        )
        return (
            f"Most recently on frame {frame} from {camera_id}, no configured targets were observed. "
            f"The last notable observation was frame {previous_notable.get('frame_seq')}: {notable_report}"
        ).strip()

    return f"Most recently on frame {frame} from {camera_id}, {compact_string(last.get('summary'), limit=300)}".strip()


def update_conversation_context(state: dict[str, Any], detection_payload: dict[str, Any]) -> dict[str, Any]:
    observation = observation_from_detection(detection_payload)
    recent = state.get("recent_observations")
    if not isinstance(recent, list):
        recent = []
    recent = [item for item in recent if isinstance(item, dict)]
    recent.append(observation)
    recent = recent[-10:]
    state["recent_observations"] = recent
    state["last_observation"] = observation
    state["conversation_context"] = {
        "what_happened": what_happened_summary(recent),
        "last_observation": observation,
        "recent_observations": recent[-5:],
        "attention_instruction": compact_string(state.get("attention_instruction"), limit=500),
    }
    return observation


def frame_observed_event(observation: dict[str, Any], conversation_summary: str = "") -> dict[str, Any]:
    return {
        "type": "cctv_operator_frame_observed",
        "payload": {
            "scene_understanding": observation.get("scene_understanding"),
            "goal_event": observation.get("goal_event"),
            "monitoring_goal": observation.get("monitoring_goal"),
            "risk_predictions": observation.get("risk_predictions"),
            "site_findings": observation.get("site_findings", []),
            "site_context": observation.get("site_context", {}),
            "site_coverage": observation.get("site_coverage", {}),
            "uncertainties": observation.get("uncertainties"),
            "capture_started_at": observation.get("capture_started_at"),
            "capture_ended_at": observation.get("capture_ended_at"),
            "frame_timestamps": observation.get("frame_timestamps"),
            "timestamp_basis": observation.get("timestamp_basis"),
            "source_profile": observation.get("source_profile"),
            "analyzed_at": observation.get("analyzed_at"),
            "camera_id": observation.get("camera_id"),
            "frame_seq": observation.get("frame_seq"),
            "video_position_seconds": observation.get("video_position_seconds"),
            "source_mode": observation.get("source_mode"),
            "source_uri": observation.get("source_uri"),
            "source_name": observation.get("source_name"),
            "source_index": observation.get("source_index"),
            "source_count": observation.get("source_count"),
            "stream_id": observation.get("stream_id"),
            "detected_target": observation.get("detected_target"),
            "detection_count": observation.get("detection_count"),
            "confidence": observation.get("confidence"),
            "risk_level": observation.get("risk_level"),
            "summary": observation.get("summary"),
            "detection_report": observation.get("detection_report"),
            "activity_description": observation.get("activity_description"),
            "visible_subjects": observation.get("visible_subjects"),
            "attention_instruction": observation.get("attention_instruction"),
            "instruction_revision": observation.get("instruction_revision"),
            "sampling_trigger": observation.get("sampling_trigger"),
            "frame_batch_ref": observation.get("frame_batch_ref"),
            "batch_id": observation.get("batch_id"),
            "candidate_count": observation.get("candidate_count"),
            "selected_count": observation.get("selected_count"),
            "command_id": observation.get("command_id"),
            "model_latency_ms": observation.get("model_latency_ms"),
            "sampling_metrics": observation.get("sampling_metrics"),
            "observed_at": observation.get("observed_at"),
            "configured_targets": observation.get("configured_targets"),
            "matched_alert_targets": observation.get(
                "matched_alert_targets"
            ),
            "alert_decision": observation.get("alert_decision"),
            "conversation_summary": conversation_summary or what_happened_summary([observation]),
        },
    }

