"""Select completed camera findings worth bringing into the conversation."""

import hashlib
import json
import math


def _text(value, limit=1800):
    return " ".join(str(value or "").split())[:limit]


def _event(kind, observation, message, identity, *, review=False, frames=None):
    captured = _text(observation.get("observed_at"), 80)
    analyzed = _text(observation.get("analyzed_at"), 80)
    qualification = ("Recorded demo playback; capture times describe playback, not a live site event."
                     if observation.get("source_profile") == "bundled_demo" else
                     "Sampled camera evidence; this does not establish continuous coverage or site-policy compliance.")
    details = [{"label": "Captured", "value": captured}, {"label": "Analyzed", "value": analyzed}]
    if frames:
        details.append({"label": "Evidence frames", "value": ", ".join(map(str, frames))})
    return {"type": kind, "timestamp": captured,
            "event_id": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32],
            "summary": f"{message}\n\nCaptured at {captured}. Analysis completed at {analyzed}.\n\n{qualification}",
            "details": details, "requires_review": review}


def conversation_findings(observations, monitoring, run_id):
    """One first result per applied goal, plus distinct evidenced risk forecasts.

    Stable identities let the SDK exchange retain the original captured result
    across polling, restart and bounded report-history rotation. A forecast is
    never promoted to a confirmed goal match or a safety violation.
    """
    revision = int(monitoring.get("instruction_revision") or 0)
    events, seen_risks, first = [], set(), True
    for observation in observations:
        if (int(observation.get("instruction_revision") or 0) != revision
                or (observation.get("alert_decision") or {}).get("reason") == "superseded_monitoring_instruction"):
            continue
        if not observation.get("observed_at") or not observation.get("analyzed_at"):
            continue
        if first and revision > 0 and not (observation.get("alert_decision") or {}).get("notify"):
            outcome = ("The model reported a possible match to the requested condition. Review the evidence before confirming it."
                       if observation.get("detected_target") else
                       "The requested condition was not confirmed in this sample; this does not rule it out.")
            account = _text(observation.get("scene_understanding") or observation.get("summary"))
            uncertainty = " ".join(_text(item, 200) for item in (observation.get("uncertainties") or [])[:3])
            events.append(_event("Monitoring result", observation,
                f"First completed analysis for the updated goal: {_text(observation.get('monitoring_goal'), 500)}\n\n"
                f"{outcome}\n\n{account}" + (f"\n\nUncertainty: {uncertainty}" if uncertainty else ""),
                ["goal-result", run_id, observation.get("camera_id"), revision]))
        first = False
        for risk in (observation.get("risk_predictions") or [])[:2]:
            if not isinstance(risk, dict):
                continue
            frames = risk.get("evidence_frames")
            count = int(observation.get("selected_count") or len(observation.get("frame_timestamps") or []))
            confidence = risk.get("confidence")
            if (risk.get("severity") not in {"medium", "high"}
                    or type(confidence) not in (int, float) or not math.isfinite(confidence) or not .55 <= confidence <= 1
                    or not isinstance(frames, list) or not frames
                    or any(type(index) is not int or not 1 <= index <= count for index in frames)
                    or len(set(frames)) != len(frames)
                    or not all(_text(risk.get(key)) for key in ("risk", "visible_evidence", "time_horizon", "recommended_review"))):
                continue
            identity = ["risk", run_id, observation.get("camera_id"), revision,
                        _text(risk["risk"], 200).casefold(), risk["severity"]]
            signature = tuple(identity)
            if signature in seen_risks:
                continue
            seen_risks.add(signature)
            # A confirmed notice already carries its associated forecasts.
            if (observation.get("alert_decision") or {}).get("notify"):
                continue
            events.append(_event("Possible risk", observation,
                f"Possible risk — {_text(risk['risk'], 200)} ({risk['severity']}).\n\n"
                f"Visible evidence: {_text(risk['visible_evidence'], 500)}\n\n"
                f"Time horizon: {_text(risk['time_horizon'], 120)}.\n\n"
                f"Review: {_text(risk['recommended_review'], 500)}\n\n"
                "This is a model forecast, not a confirmed incident. Review the selected frames before acting.",
                identity, review=True, frames=frames))
    return events
