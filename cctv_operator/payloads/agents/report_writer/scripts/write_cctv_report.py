#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
for ancestor in (SCRIPT_DIR, *SCRIPT_DIR.parents):
    if (ancestor / "domain").is_dir() and str(ancestor) not in sys.path:
        sys.path.insert(0, str(ancestor))
        break

from domain.reporting import bounded_history, sampling_records


RESULT_START = "__MN_RESULT_START__"
RESULT_END = "__MN_RESULT_END__"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def input_payload() -> dict[str, Any]:
    input_file = os.environ.get("MN_INPUT_FILE")
    if not input_file:
        return {}
    incoming = read_json(Path(input_file))
    sandbox = incoming.get("sandbox") if isinstance(incoming.get("sandbox"), dict) else {}
    raw_stdout = sandbox.get("stdout")
    if isinstance(raw_stdout, str) and raw_stdout.strip():
        try:
            decoded = json.loads(raw_stdout)
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            return decoded
    return incoming


def event_payloads(events: list[Any], event_type: str) -> list[dict[str, Any]]:
    return [
        event.get("payload")
        for event in events
        if isinstance(event, dict)
        and event.get("type") == event_type
        and isinstance(event.get("payload"), dict)
    ]


def merge_report(previous: dict[str, Any], detector: dict[str, Any]) -> dict[str, Any]:
    events = detector.get("events") if isinstance(detector.get("events"), list) else []
    state = detector.get("next_state") if isinstance(detector.get("next_state"), dict) else {}
    observed = event_payloads(events, "cctv_operator_frame_observed")
    detections = event_payloads(events, "cctv_operator_detection")
    errors = event_payloads(events, "cctv_operator_frame_analysis_failed")
    alerts = [
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
    sampling_history = bounded_history(previous.get("sampling"), sampling, limit=500)
    history = [*history, *observed][-500:]
    detection_history = [*detection_history, *detections][-500:]
    error_history = [*error_history, *errors][-100:]
    alert_history = [*alert_history, *alerts][-100:]

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
    lines = [
        "# CCTV Operator Report",
        "",
        f"- Source mode: {report['source_mode']}",
        f"- Media accelerator: {report['media_accelerator']}",
        f"- Frames analyzed: {report['frames_analyzed']}",
        f"- Target detections: {report['detection_count']}",
        f"- Alert records: {len(report['alerts'])}",
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
    lines.extend(["", "## Latest observations"])
    observations = report["observations"][-20:]
    if not observations:
        lines.append("- No observations are available yet.")
    for item in observations:
        source = item.get("source_name") or item.get("source_uri") or "unknown source"
        lines.append(
            f"- Frame {item.get('frame_seq', '?')} · {source} · "
            f"confidence {float(item.get('confidence') or 0):.2f}: {item.get('summary') or 'No summary.'}"
        )
    lines.extend(["", "## Review boundary", "", report["review_boundary"]])
    return "\n".join(lines) + "\n"


def final_artifact(report: dict[str, Any]) -> dict[str, Any]:
    has_errors = bool(report["errors"])
    return {
        "type": "cctv_operator_review",
        "executive_summary": (
            f"Analyzed {report['frames_analyzed']} frame(s) from {len(report['sources_observed'])} source(s) "
            f"and recorded {report['detection_count']} configured-target detection(s)."
        ),
        "recommended_action": (
            "Review media decode or model errors before relying on the observations."
            if has_errors
            else "Review the detection timeline and confirm any safety or security response with a person."
        ),
        "confidence": 0.55 if has_errors else 0.78,
        "evidence": [
            {"source": "cctv_report.json", "detail": "Structured source, frame, detection, alert, and error history."},
            {"source": "events.jsonl", "detail": "Append-only runtime observation and human-notice events."},
        ],
        "next_steps": [
            "Inspect configured-target detections and source timestamps.",
            "Confirm significant observations against the original video or live stream.",
            "Tune visual targets, confidence, and cooldown policy if needed.",
        ],
        "source_refs": ["cctv_report.json", "cctv_report.md", "events.jsonl"],
    }


def emit_result(payload: dict[str, Any]) -> None:
    envelope = {"exit_code": 0, "stdout": json.dumps(payload, sort_keys=True), "stderr": ""}
    print(f"{RESULT_START}{json.dumps(envelope, sort_keys=True)}{RESULT_END}")


def configured_run_dir() -> Path:
    explicit = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()

    runs_root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    run_id = str(os.environ.get("MN_RUN_ID") or "").strip()
    if runs_root and run_id:
        return Path(runs_root).expanduser() / run_id
    return Path(".")


def main() -> int:
    run_dir = configured_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "cctv_report.json"
    report = merge_report(read_json(report_path), input_payload())
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "cctv_report.md").write_text(markdown_report(report), encoding="utf-8")
    artifact = final_artifact(report)
    (run_dir / "final_artifact.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    emit_result({"report": report, "final_artifact": artifact})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
