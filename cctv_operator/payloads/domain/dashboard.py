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


def _runtime_event_summary(event_type: str, payload: Mapping[str, Any]) -> str:
    explicit = (
        payload.get("summary")
        or payload.get("message")
        or payload.get("reason")
        or payload.get("error")
        or payload.get("detail")
    )
    if explicit:
        return str(explicit)
    if event_type == "cctv_operator_frame_batch_ready":
        count = int(payload.get("selected_count") or 0)
        trigger = str(payload.get("trigger") or payload.get("sampling_trigger") or "scheduled")
        return f"Selected {count} frame(s) for {trigger.replace('_', ' ')} analysis."
    if event_type == "cctv_operator_frame_observed":
        count = int(payload.get("selected_count") or 0)
        return f"Visual analysis completed for a {count}-frame evidence batch."
    if event_type == "cctv_operator_report_ready":
        return "The cumulative operator report was updated."
    if event_type == "cctv_operator_burst_started":
        return "A sustained scene change started an evidence burst."
    if event_type == "cctv_operator_burst_completed":
        return "The scene-change evidence burst completed."
    if event_type == "video_monitor_start":
        return "The video source was validated and monitoring started."
    if event_type == "run_started":
        return "The CCTV monitoring run started."
    status = payload.get("status") or payload.get("phase")
    return f"Operator state changed to {status}." if status else ""


def _runtime_event_label(event_type: str) -> str:
    labels = {
        "cctv_operator_frame_batch_ready": "Evidence selected",
        "cctv_operator_frame_observed": "Frame analyzed",
        "cctv_operator_report_ready": "Report updated",
        "cctv_operator_burst_started": "Scene burst",
        "cctv_operator_burst_completed": "Burst completed",
        "cctv_operator_sample_skipped": "Sample skipped",
        "cctv_operator_queue_lag": "Queue delayed",
        "cctv_operator_attention_updated": "Monitoring focus",
        "cctv_operator_frame_analysis_failed": "Analysis error",
        "video_monitor_start": "Monitor online",
        "run_started": "Run started",
    }
    if event_type in labels:
        return labels[event_type]
    return " ".join(event_type.replace("cctv_operator_", "").split("_")).title()


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
        event_type = str(event.get("type") or "runtime_event")
        if event_type == "cctv_operator_sample_due":
            continue
        recent_events.append(
            _event(
                _runtime_event_label(event_type),
                _runtime_event_summary(event_type, payload_value),
                timestamp=event.get("timestamp") or event.get("ts"),
            )
        )
    indexed_events = [
        (index, event)
        for index, event in enumerate(recent_events)
        if event["summary"]
    ]
    indexed_events.sort(
        key=lambda item: (_epoch(item[1]["timestamp"]) or 0.0, item[0]),
        reverse=True,
    )
    recent_events = []
    seen: set[tuple[str, str, str]] = set()
    for _index, event in indexed_events:
        identity = (event["type"], event["timestamp"], event["summary"])
        if identity in seen:
            continue
        seen.add(identity)
        recent_events.append(event)
        if len(recent_events) >= 50:
            break

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
