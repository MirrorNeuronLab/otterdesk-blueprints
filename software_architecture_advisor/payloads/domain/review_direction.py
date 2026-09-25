"""Offer a bounded, report-bound conversation choice after publication."""
import hashlib
from pathlib import Path

from mn_sdk.blueprint_support import append_human_event, read_human_events


def publish_review_direction(context, report):
    """Record one choice per immutable report digest; never start work from a click."""
    run_dir = Path(context["run_dir"])
    run_id = str(context.get("run_id") or run_dir.name)
    runs_root = run_dir.parent
    digest = hashlib.sha256((run_dir / "report.json").read_bytes()).hexdigest()
    request_id = f"architecture-review-{digest[:24]}"
    existing = read_human_events(run_id, runs_root=runs_root)
    closed = {
        (event.get("payload") or {}).get("request_id")
        for event in existing
        if event.get("type") in {"human_input_received", "human_input_timeout", "human_decision_applied"}
    }
    for event in existing:
        payload = event.get("payload") or {}
        previous_id = payload.get("request_id")
        if (
            event.get("type") == "human_input_requested"
            and payload.get("decision_type") == "architecture_review_direction"
            and previous_id not in closed
            and previous_id != request_id
        ):
            append_human_event(
                run_id,
                "human_input_timeout",
                {"request_id": previous_id, "reason": "superseded_report"},
                runs_root=runs_root,
                blueprint_id="software_architecture_advisor",
            )
    if not any(
        event.get("type") == "human_input_requested"
        and (event.get("payload") or {}).get("request_id") == request_id
        for event in existing
    ):
        findings = report.get("findings") or []
        reviewed = sum(
            1 for finding in findings
            if (finding.get("review") or finding.get("assessment") or {}).get("verdict")
        )
        structural = report.get("structural_analysis") or {}
        summary = (
            "The architecture review is ready, with an evidence-linked dependency "
            "baseline and suggested next steps."
        )
        if report.get("status") == "partial":
            summary = "The available architecture review is partial. Check its coverage before acting."
        append_human_event(
            run_id,
            "human_input_requested",
            {
                "request_id": request_id,
                "decision_type": "architecture_review_direction",
                "decision_digest": digest,
                "interaction_kind": "judgment",
                "blocking": False,
                "summary": summary,
                "prompt": "Which direction should guide the next architecture task?",
                "context": [
                    {"label": "Review", "value": "Partial" if report.get("status") == "partial" else "Ready"},
                    {"label": "Findings", "value": f"{reviewed} assessed of {len(findings)}"},
                    {"label": "Dependency baseline", "value": f"{structural.get('dependency_edges', 0)} static edges"},
                ],
                "options": [
                    {"label": "Prioritize a change", "description": "Select a reviewed finding and verify its current evidence before implementation."},
                    {"label": "Challenge a finding", "description": "Examine counter-evidence and alternatives before accepting a recommendation."},
                    {"label": "Investigate further", "description": "Focus a new analysis on coverage gaps or an unresolved boundary."},
                    {"label": "Defer", "description": "Keep this review for reference without starting another task."},
                ],
            },
            runs_root=runs_root,
            blueprint_id="software_architecture_advisor",
        )
    return {"request_id": request_id, "decision_digest": digest}
