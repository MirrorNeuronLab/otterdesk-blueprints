from __future__ import annotations

import re
import time
from typing import Any, Mapping


DEFAULT_VISUAL_TARGETS = (
    "person",
    "unattended package",
    "restricted-area entry",
)
DEFAULT_ALERT_POLICY = {
    "mode": "human_notice_only",
    "min_confidence": 0.55,
    "cooldown_seconds": 120.0,
    "notify_on": list(DEFAULT_VISUAL_TARGETS),
}


def _payload_config(config: Mapping[str, Any] | None) -> Mapping[str, Any]:
    inputs = (config or {}).get("inputs")
    if not isinstance(inputs, Mapping):
        return {}
    payload = inputs.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _clean_phrases(value: Any, *, fallback: tuple[str, ...]) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else []
    cleaned: list[str] = []
    for item in values:
        text = " ".join(str(item or "").split()).strip()[:160]
        if text and text.casefold() not in {entry.casefold() for entry in cleaned}:
            cleaned.append(text)
    return cleaned or list(fallback)


def configured_visual_targets(
    config: Mapping[str, Any] | None,
) -> list[str]:
    return _clean_phrases(
        _payload_config(config).get("visual_targets"),
        fallback=DEFAULT_VISUAL_TARGETS,
    )


def configured_alert_policy(
    config: Mapping[str, Any] | None,
    *,
    visual_targets: list[str] | None = None,
) -> dict[str, Any]:
    raw = _payload_config(config).get("alert_policy")
    raw = raw if isinstance(raw, Mapping) else {}
    targets = visual_targets or configured_visual_targets(config)
    notify_on = _clean_phrases(
        raw.get("notify_on"),
        fallback=tuple(targets),
    )
    try:
        confidence = min(1.0, max(0.0, float(raw.get("min_confidence", 0.55))))
    except (TypeError, ValueError):
        confidence = 0.55
    try:
        cooldown = max(0.0, float(raw.get("cooldown_seconds", 120.0)))
    except (TypeError, ValueError):
        cooldown = 120.0
    mode = str(raw.get("mode") or "human_notice_only").strip().lower()
    if mode not in {"human_notice_only", "human_notice_and_slack"}:
        mode = "human_notice_only"
    return {
        "mode": mode,
        "min_confidence": confidence,
        "cooldown_seconds": cooldown,
        "notify_on": notify_on,
    }


def target_prompt_text(targets: list[str]) -> str:
    if len(targets) == 1:
        return targets[0]
    return ", ".join(targets[:-1]) + f", or {targets[-1]}"


def _normalized_text(value: Any) -> str:
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split()
    )


def detection_search_text(detection: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("detected_types", "visible_subjects"):
        value = detection.get(key)
        if isinstance(value, list):
            parts.extend(str(item or "") for item in value)
    detections = detection.get("detections")
    if isinstance(detections, list):
        for item in detections:
            if isinstance(item, Mapping):
                parts.extend(
                    str(item.get(key) or "")
                    for key in ("label", "category", "activity")
                )
    if not any(part.strip() for part in parts):
        parts.extend(
            str(detection.get(key) or "")
            for key in (
                "summary",
                "detection_report",
                "activity_description",
            )
        )
    return _normalized_text(" ".join(parts))


def matched_notification_targets(
    detection: Mapping[str, Any],
    notify_on: list[str],
) -> list[str]:
    haystack = f" {detection_search_text(detection)} "
    matches = []
    for target in notify_on:
        needle = _normalized_text(target)
        if needle and f" {needle} " in haystack:
            matches.append(target)
    return matches


def evaluate_alert(
    detection: Mapping[str, Any],
    policy: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    evaluated_at = float(time.time() if now is None else now)
    detected = bool(detection.get("detected_target"))
    try:
        confidence = min(1.0, max(0.0, float(detection.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    threshold = float(policy.get("min_confidence", 0.55))
    cooldown = float(policy.get("cooldown_seconds", 120.0))
    notify_on = list(policy.get("notify_on") or [])
    matched = matched_notification_targets(detection, notify_on)
    elapsed = evaluated_at - float(state.get("last_alert_wall_ts", 0.0) or 0.0)

    if not detected:
        reason = "no_configured_target_detected"
    elif confidence < threshold:
        reason = "below_confidence_threshold"
    elif not matched:
        reason = "target_not_in_notification_policy"
    elif elapsed < cooldown:
        reason = "cooldown_active"
    else:
        reason = "notify_reviewer"
    return {
        "notify": reason == "notify_reviewer",
        "reason": reason,
        "matched_targets": matched,
        "confidence": confidence,
        "min_confidence": threshold,
        "cooldown_seconds": cooldown,
        "mode": str(policy.get("mode") or "human_notice_only"),
        "evaluated_at": evaluated_at,
    }


def configured_target_notice(
    detection: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    camera_id = str(detection.get("camera_id") or "cctv")[:80]
    frame_seq = detection.get("frame_seq")
    matches = list(decision.get("matched_targets") or [])
    target_text = ", ".join(matches) or "configured target"
    detail = str(
        detection.get("detection_report")
        or detection.get("summary")
        or "A configured target was observed."
    )[:700]
    return {
        "type": "human_notice",
        "channel": "human",
        "payload": {
            "notice_id": f"cctv-target-{camera_id}-{frame_seq}",
            "kind": "configured_target_detection",
            "level": (
                "urgent"
                if str(detection.get("risk_level") or "").lower() == "high"
                else "attention"
            ),
            "title": f"Review {target_text}",
            "message": detail,
            "detail": detail,
            "camera_id": camera_id,
            "frame_seq": frame_seq,
            "confidence": decision.get("confidence"),
            "risk_level": detection.get("risk_level"),
            "matched_targets": matches,
            "observed_at": detection.get("observed_at"),
            "frame_batch_ref": detection.get("frame_batch_ref"),
            "chat_delivery": "otterdesk_worker_chat",
            "requires_ack": True,
        },
    }
