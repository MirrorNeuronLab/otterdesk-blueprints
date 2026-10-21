"""Interpret visual findings using the CCTV observation and risk policy."""

from typing import Any
import json
from .video_understanding import understanding_fields

def normalize_detection(result: dict[str, Any]) -> dict[str, Any]:
    raw_confidence = result.get("confidence")
    has_top_level_confidence = raw_confidence is not None
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
        has_top_level_confidence = False

    detected = result.get("detected_target", result.get("detected", False))
    if isinstance(detected, str):
        normalized_detected = detected.strip().lower()
        if normalized_detected in {"true", "yes", "1", "detected", "visible", "present", "active"}:
            detected = True
        elif normalized_detected in {"false", "no", "0", "none", "absent", "not_detected"}:
            detected = False
        else:
            detected = result.get("detected", False)

    detections = result.get("detections", result.get("observed_items", []))
    if isinstance(detections, dict):
        detections = [detections]
    if not isinstance(detections, list):
        detections = []

    normalized_detections: list[dict[str, Any]] = []
    for item in detections[:20]:
        if isinstance(item, dict):
            label = str(item.get("label", item.get("name", item.get("type", "observed item")))).strip()[:80] or "observed item"
            normalized_detections.append(
                {
                    "label": label,
                    "category": str(item.get("category", item.get("type", label))).strip()[:80] or label,
                    "color": str(
                        item.get("color", item.get("visible_color", "unknown"))
                    ).strip()[:60]
                    or "unknown",
                    "position": str(item.get("position", item.get("location", ""))).strip()[:160],
                    "activity": str(item.get("activity", item.get("movement", ""))).strip()[:160],
                    "confidence": safe_confidence(item.get("confidence", confidence)),
                }
            )
        elif str(item).strip():
            normalized_detections.append(
                {
                    "label": str(item).strip()[:80],
                    "category": "observed item",
                    "color": "unknown",
                    "position": "",
                    "activity": "",
                    "confidence": safe_confidence(confidence),
                }
            )

    if normalized_detections and not has_top_level_confidence:
        confidence = max(item["confidence"] for item in normalized_detections)

    detection_count = result.get("detection_count", len(normalized_detections) if detected else 0)
    try:
        detection_count = max(0, int(detection_count))
    except (TypeError, ValueError):
        detection_count = len(normalized_detections) if detected else 0

    risk_level = str(result.get("risk_level", "low")).lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium" if detected else "low"

    summary = str(result.get("summary", "")).strip()
    if not summary:
        summary = f"{detection_count} configured target(s) were observed in the monitored scene." if detected else "No configured targets were observed in the monitored scene."

    raw_report = result.get("detection_report", result.get("description", ""))
    if isinstance(raw_report, list):
        detection_report = " ".join(
            item.strip() for item in raw_report[:20]
            if isinstance(item, str) and item.strip()
        )
    else:
        detection_report = raw_report.strip() if isinstance(raw_report, str) else ""
    if not detection_report and detected:
        details = []
        for detection in normalized_detections:
            label = " ".join(
                part for part in [detection.get("color"), detection.get("label")] if part and part != "unknown"
            )
            details.append(label or detection.get("label") or "observed item")
        detection_report = f"{detection_count} detection(s): {', '.join(details)}." if details else summary

    activity_description = str(result.get("activity_description", result.get("activity", ""))).strip()
    if not activity_description and detected:
        activity_description = "Activity is not clearly visible."

    detected_types = result.get("detected_types", result.get("categories", []))
    if not isinstance(detected_types, list):
        detected_types = [str(detected_types)]
    if not detected_types and normalized_detections:
        detected_types = [detection["category"] for detection in normalized_detections]

    detected_colors = result.get("detected_colors", [])
    if not isinstance(detected_colors, list):
        detected_colors = [str(detected_colors)]
    if not detected_colors and normalized_detections:
        detected_colors = [detection["color"] for detection in normalized_detections if detection["color"]]

    appearance_notes = result.get("appearance_notes", [])
    if not isinstance(appearance_notes, list):
        appearance_notes = [str(appearance_notes)]

    visible_subjects = result.get("visible_subjects", [])
    if not isinstance(visible_subjects, list):
        visible_subjects = [str(visible_subjects)]

    return {
        **understanding_fields(result),
        "goal_event": result.get("goal_event"),
        "site_findings": result.get("site_findings", []),
        "detected": bool(detected),
        "detected_target": bool(detected),
        "detection_count": detection_count,
        "detections": normalized_detections,
        "confidence": max(0.0, min(confidence, 1.0)),
        "summary": summary[:500],
        "detection_report": detection_report[:900],
        "activity_description": activity_description[:700],
        "detected_types": [str(item)[:80] for item in detected_types[:12] if str(item).strip()],
        "detected_colors": [str(item)[:60] for item in detected_colors[:12] if str(item).strip()],
        "appearance_notes": [str(item)[:120] for item in appearance_notes[:8] if str(item).strip()],
        "risk_level": risk_level,
        "visible_subjects": [str(item)[:80] for item in visible_subjects[:8]],
    }


def safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_string(value: Any, limit: int = 500) -> str:
    text = "" if value is None else " ".join(str(value).split())
    return text[:limit]


def normalize_attention_instruction(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return compact_string(", ".join(item for item in (normalize_attention_instruction(item) for item in value) if item))
    if isinstance(value, dict):
        parts = []
        for key in ("target", "label", "detail", "description", "zone", "color", "activity"):
            text = compact_string(value.get(key), limit=120)
            if text:
                parts.append(f"{key}: {text}")
        if parts:
            return compact_string("; ".join(parts))
        try:
            return compact_string(json.dumps(value, sort_keys=True))
        except TypeError:
            return compact_string(value)
    return compact_string(value)

