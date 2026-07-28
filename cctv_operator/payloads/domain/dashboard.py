from __future__ import annotations

import datetime as dt
import time
from typing import Any, Mapping


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _display_time(value: Any) -> str:
    if value in (None, ""):
        return "waiting"
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(
            float(value), tz=dt.timezone.utc
        ).isoformat().replace("+00:00", "Z")
    return str(value)[:80]


def _epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _event(
    event_type: str,
    summary: str,
    *,
    timestamp: Any = "",
) -> dict[str, str]:
    return {
        "type": event_type,
        "timestamp": _display_time(timestamp) if timestamp else "",
        "summary": " ".join(str(summary or "").split())[:500],
    }


def operator_state(
    *,
    run_id: str,
    config: Mapping[str, Any],
    report: Mapping[str, Any],
    latest_frame: Mapping[str, Any],
    monitoring: Mapping[str, Any],
    supplemental_events: list[Mapping[str, Any]],
    preview_status: str,
    preview_warning: str,
    now: float | None = None,
) -> dict[str, Any]:
    observations = _items(report.get("observations"))
    detections = _items(report.get("detections"))
    alerts = _items(report.get("alerts"))
    errors = _items(report.get("errors"))
    sampling_metrics = _mapping(report.get("sampling_metrics"))
    latest = observations[-1] if observations else {}
    latest_detection = detections[-1] if detections else {}
    latest_batch = _mapping(report.get("latest_batch"))
    payload = _mapping(_mapping(config.get("inputs")).get("payload"))
    configured_targets = payload.get("visual_targets")
    configured_targets = (
        [str(item) for item in configured_targets if str(item).strip()]
        if isinstance(configured_targets, list)
        else []
    )
    watch_target = str(monitoring.get("instruction") or "").strip()
    watch_target = watch_target or ", ".join(configured_targets) or "Default visual targets"

    last_seen = (
        latest.get("observed_at")
        or latest_frame.get("analyzed_at")
        or latest_frame.get("updated_at")
        or latest_frame.get("created_at")
    )
    last_seen_epoch = _epoch(last_seen)
    baseline = _mapping(config.get("sampling")).get(
        "baseline_interval_seconds", 20
    )
    try:
        stale_after = max(60.0, float(baseline) * 3.0)
    except (TypeError, ValueError):
        stale_after = 60.0
    current_time = float(time.time() if now is None else now)
    stale = (
        last_seen_epoch is not None
        and current_time - last_seen_epoch > stale_after
    )

    review_alerts = [
        alert
        for alert in alerts
        if str(alert.get("status") or "review").lower()
        not in {"resolved", "dismissed"}
    ]
    if errors:
        status = "Analysis error"
        warning = str(errors[-1].get("error") or "Frame analysis needs attention.")[:500]
    elif stale:
        status = "Analysis delayed"
        warning = (
            f"No analyzed frame has arrived within {int(stale_after)} seconds. "
            "Preview may continue while sparse analysis is delayed."
        )
    elif review_alerts:
        status = "Review needed"
        warning = f"{len(review_alerts)} operator notice(s) need review."
    elif observations:
        status = "Monitoring"
        warning = preview_warning
    else:
        status = "Starting"
        warning = preview_warning or "Waiting for the first selected frame to be analyzed."

    recent_events: list[dict[str, str]] = []
    for error in errors[-10:]:
        recent_events.append(
            _event(
                "Analysis error",
                str(error.get("error") or "A selected frame could not be analyzed."),
                timestamp=error.get("observed_at"),
            )
        )
    for alert in alerts[-20:]:
        recent_events.append(
            _event(
                "Operator notice",
                str(
                    alert.get("message")
                    or alert.get("detail")
                    or alert.get("summary")
                    or "A configured target needs review."
                ),
                timestamp=alert.get("observed_at"),
            )
        )
    for detection in detections[-20:]:
        recent_events.append(
            _event(
                "Target observed",
                str(
                    detection.get("detection_report")
                    or detection.get("summary")
                    or "A configured target was observed."
                ),
                timestamp=detection.get("observed_at"),
            )
        )
    for event in supplemental_events[-20:]:
        payload_value = _mapping(event.get("payload"))
        recent_events.append(
            _event(
                str(event.get("type") or "Runtime event"),
                str(
                    payload_value.get("summary")
                    or payload_value.get("reason")
                    or payload_value.get("error")
                    or ""
                ),
                timestamp=event.get("timestamp") or event.get("ts"),
            )
        )
    recent_events = [event for event in recent_events if event["summary"]][-50:]

    finding = (
        latest_detection.get("detection_report")
        or latest_detection.get("summary")
        or latest.get("summary")
        or "Waiting for the first analyzed frame."
    )
    confidence = latest_detection.get("confidence", latest.get("confidence"))
    confidence_text = (
        f"{float(confidence):.0%}" if confidence is not None else "waiting"
    )
    return {
        "metrics": {
            "status": status,
            "run": run_id,
            "watch target": watch_target,
            "latest finding": str(finding)[:300],
            "confidence": confidence_text,
            "risk": str(
                latest_detection.get("risk_level")
                or latest.get("risk_level")
                or "waiting"
            ),
            "frames analyzed": int(report.get("frames_analyzed") or len(observations)),
            "target detections": int(report.get("detection_count") or len(detections)),
            "alerts to review": len(review_alerts),
            "last analyzed": _display_time(last_seen),
            "model latency": (
                f"{int(sampling_metrics.get('latest_model_latency_ms') or 0)} ms"
                if observations
                else "waiting"
            ),
            "latest trigger": str(
                latest_batch.get("sampling_trigger")
                or latest_batch.get("trigger")
                or "waiting"
            ),
            "selected frames": int(latest_batch.get("selected_count") or 0),
            "samples skipped": int(sampling_metrics.get("samples_skipped") or 0),
            "preview": preview_status,
            "instruction revision": int(
                monitoring.get("instruction_revision") or 0
            ),
        },
        "warning": warning,
        "events": recent_events,
    }
