from __future__ import annotations

from typing import Any, Mapping

from .site_reports import sections as site_sections


SAMPLING_EVENT_TYPES = {
    "cctv_operator_scene_change_detected",
    "cctv_operator_burst_started",
    "cctv_operator_burst_completed",
    "cctv_operator_frame_batch_ready",
    "cctv_operator_sample_skipped",
    "cctv_operator_queue_lag",
}


def sampling_records(events: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": str(event.get("type")),
            **dict(event.get("payload") or {}),
        }
        for event in events
        if isinstance(event, Mapping)
        and event.get("type") in SAMPLING_EVENT_TYPES
        and isinstance(event.get("payload"), Mapping)
    ]


def bounded_history(previous: Any, current: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    history = previous if isinstance(previous, list) else []
    return [*history, *current][-limit:]


def event_payloads(events: list[Any], event_type: str) -> list[dict[str, Any]]:
    return [
        event.get("payload")
        for event in events
        if isinstance(event, dict)
        and event.get("type") == event_type
        and isinstance(event.get("payload"), dict)
    ]


def merge_report(previous: dict[str, Any], events: list, state: dict) -> dict[str, Any]:
    observed = event_payloads(events, "cctv_operator_frame_observed")
    detections = event_payloads(events, "cctv_operator_detection")
    errors = event_payloads(events, "cctv_operator_frame_analysis_failed")
    alerts = event_payloads(events, "human_notice")
    deliveries = [
        event.get("payload")
        for event in events
        if isinstance(event, dict)
        and str(event.get("type") or "").startswith("cctv_operator_slack_alert_")
        and isinstance(event.get("payload"), dict)
    ]
    sampling = sampling_records(events)
    sampling.extend(
        {
            "type": "cctv_operator_frame_batch_ready",
            "trigger": item.get("sampling_trigger"),
            "instruction_revision": item.get("instruction_revision"),
            "frame_batch_ref": item.get("frame_batch_ref"),
            "batch_id": item.get("batch_id"),
            "candidate_count": item.get("candidate_count"),
            "selected_count": item.get("selected_count"),
            "model_latency_ms": item.get("model_latency_ms"),
            "metrics": item.get("sampling_metrics") or {},
        }
        for item in observed
        if item.get("frame_batch_ref")
    )

    history = previous.get("observations") if isinstance(previous.get("observations"), list) else []
    detection_history = previous.get("detections") if isinstance(previous.get("detections"), list) else []
    error_history = previous.get("errors") if isinstance(previous.get("errors"), list) else []
    alert_history = previous.get("alerts") if isinstance(previous.get("alerts"), list) else []
    delivery_history = previous.get("alert_deliveries") if isinstance(previous.get("alert_deliveries"), list) else []
    sampling_history = bounded_history(previous.get("sampling"), sampling, limit=500)
    history = [*history, *observed][-500:]
    detection_history = [*detection_history, *detections][-500:]
    error_history = [*error_history, *errors][-100:]
    alert_history = [*alert_history, *alerts][-100:]
    delivery_history = [*delivery_history, *deliveries][-100:]

    source_names = sorted(
        {
            str(item.get("source_name") or item.get("source_uri") or "unknown")
            for item in history
            if isinstance(item, dict)
        }
    )
    return {
        "schema": "otterdesk.cctv_operator_report.v2",
        "blueprint_id": "cctv_operator",
        "source_mode": state.get("source_mode") or previous.get("source_mode") or "unknown",
        "media_accelerator": "nvidia_cuda",
        "frames_analyzed": int(state.get("frames_seen") or len(history)),
        "detection_count": int(state.get("detections") or len(detection_history)),
        "sources_observed": source_names,
        "completed_sources": list(state.get("completed_sources") or previous.get("completed_sources") or []),
        "observations": history,
        "detections": detection_history,
        "alerts": alert_history,
        "alert_deliveries": delivery_history,
        "errors": error_history,
        "sampling": sampling_history,
        "sampling_metrics": {
            "batches_ready": sum(
                item.get("type") == "cctv_operator_frame_batch_ready"
                for item in sampling_history
            ),
            "scene_changes": sum(
                item.get("type") == "cctv_operator_scene_change_detected"
                for item in sampling_history
            ),
            "samples_skipped": sum(
                item.get("type") == "cctv_operator_sample_skipped"
                for item in sampling_history
            ),
            "dropped_baselines": max(
                [
                    int((item.get("metrics") or {}).get("dropped_baselines") or 0)
                    for item in sampling_history
                    if isinstance(item.get("metrics"), dict)
                ]
                or [0]
            ),
            "latest_model_latency_ms": next(
                (
                    int(item.get("model_latency_ms") or 0)
                    for item in reversed(sampling_history)
                    if item.get("model_latency_ms") is not None
                ),
                0,
            ),
        },
        "latest_batch": state.get("last_batch") or previous.get("latest_batch"),
        "monitoring": (
            {
                "instruction": observed[-1].get("attention_instruction") or "",
                "instruction_revision": int(
                    observed[-1].get("instruction_revision") or 0
                ),
                "last_command_id": observed[-1].get("command_id") or "",
            }
            if observed
            else previous.get("monitoring") or {}
        ),
        "review_boundary": "Decision support only; a human reviewer must confirm safety or security decisions.",
    }


def markdown_report(report: dict[str, Any]) -> str:
    monitoring = report.get("monitoring")
    monitoring = monitoring if isinstance(monitoring, dict) else {}
    lines = [
        "# CCTV Operator Report",
        "",
        f"- Watch target: {monitoring.get('instruction') or 'Configured visual targets'}",
        f"- Source mode: {report['source_mode']}",
        f"- Media accelerator: {report['media_accelerator']}",
        f"- Analyzed sampled sequences: {report['frames_analyzed']}",
        f"- Target detections: {report['detection_count']}",
        f"- Operator notices: {len(report['alerts'])}",
        f"- Analysis errors: {len(report['errors'])}",
        f"- Adaptive batches: {report['sampling_metrics']['batches_ready']}",
        f"- Scene changes: {report['sampling_metrics']['scene_changes']}",
        f"- Samples skipped: {report['sampling_metrics']['samples_skipped']}",
        f"- Dropped baselines: {report['sampling_metrics']['dropped_baselines']}",
        f"- Latest model latency: {report['sampling_metrics']['latest_model_latency_ms']} ms",
        "",
        "## Sources",
    ]
    if report["sources_observed"]:
        lines.extend(f"- {source}" for source in report["sources_observed"])
    else:
        lines.append("- No source frames have been observed yet.")
    lines.extend(["", "## Notices requiring review"])
    alerts = report["alerts"][-20:]
    if not alerts:
        lines.append("- No operator notices have been recorded.")
    for item in alerts:
        target = ", ".join(item.get("matched_targets") or [])
        target_suffix = f" · {target}" if target else ""
        lines.append(
            f"- Frame {item.get('frame_seq', '?')}{target_suffix}: "
            f"{item.get('message') or item.get('detail') or 'Review the linked frame evidence.'}"
        )
    lines.extend(["", "## Latest observations"])
    observations = report["observations"][-20:]
    if not observations:
        lines.append("- No observations are available yet.")
    for item in observations:
        source = item.get("source_name") or item.get("source_uri") or "unknown source"
        lines.append(
            f"- Frame {item.get('frame_seq', '?')} · {source} · "
            f"confidence {float(item.get('confidence') or 0):.2f} · "
            f"{item.get('observed_at') or 'time unavailable'}: "
            f"{item.get('summary') or 'No summary.'}"
        )
    lines.extend(["", "## Predicted risks", "", "Forecasts are possible future outcomes, not observed incidents."])
    forecasts = [(item, prediction) for item in observations for prediction in item.get("risk_predictions") or []]
    if not forecasts:
        lines.append("- No supported forecast was recorded in these sampled observations. This does not certify safety.")
    for observation, prediction in forecasts:
        lines.append(
            f"- {observation.get('observed_at')} · frame {observation.get('frame_seq')} · "
            f"{prediction['risk']} ({prediction['severity']}, model score {prediction['confidence']:.2f}, uncalibrated). "
            f"Horizon: {prediction['time_horizon']}. Evidence: {prediction['visible_evidence']}. "
            f"Review: {prediction['recommended_review']}. Batch: {observation.get('frame_batch_ref')}."
        )
    lines.extend(["", *site_sections(observations)])
    lines.extend(["", "## Analysis errors"])
    if not report["errors"]:
        lines.append("- No analysis errors have been recorded.")
    for item in report["errors"][-20:]:
        lines.append(
            f"- Frame {item.get('frame_seq', '?')}: "
            f"{item.get('error') or 'Unknown analysis error.'}"
        )
    lines.extend(["", "## Review boundary", "", report["review_boundary"]])
    return "\n".join(lines) + "\n"


def final_artifact(report: dict[str, Any]) -> dict[str, Any]:
    has_errors = bool(report["errors"])
    needs_review = bool(report["alerts"])
    return {
        "type": "cctv_operator_review",
        "executive_summary": (
            f"Analyzed {report['frames_analyzed']} sampled sequence(s) from {len(report['sources_observed'])} source(s) "
            f"and recorded {report['detection_count']} configured-target detection(s)."
        ),
        "recommended_action": (
            "Review media decode or model errors before relying on the observations."
            if has_errors
            else (
                "Review the operator notices and linked frame evidence before deciding on any response."
                if needs_review
                else "Continue monitoring; confirm any later safety or security response with a person."
            )
        ),
        "confidence": 0.55 if has_errors else (0.74 if needs_review else 0.78),
        "evidence": [
            {"source": "cctv_report.json", "detail": "Structured source, frame, detection, alert, and error history."},
            {"source": "latest_analyzed_frame.jpg", "detail": "Latest selected frame actually reviewed by the model."},
        ],
        "next_steps": [
            "Inspect configured-target detections and source timestamps.",
            "Confirm significant observations against the original video or live stream.",
            "Tune visual targets, confidence, and cooldown policy if needed.",
        ],
        "source_refs": ["cctv_report.json", "cctv_report.md", "events.jsonl"],
    }
