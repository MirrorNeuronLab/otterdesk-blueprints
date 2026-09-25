"""CCTV-specific policy for routing a sampled frame after a small vision check."""

from __future__ import annotations

from typing import Any, Mapping


GATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["condition_met", "confidence"],
    "properties": {
        "condition_met": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def normalize_gate(value: Mapping[str, Any]) -> dict[str, Any]:
    match = value.get("condition_met")
    confidence = value.get("confidence")
    if not isinstance(match, bool) or isinstance(confidence, bool):
        raise ValueError("vision gate must return a boolean condition_met and numeric confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("vision gate confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("vision gate confidence must be between zero and one")
    return {"condition_met": match, "confidence": confidence}


def branch(gate: Mapping[str, Any], *, min_confidence: float) -> str:
    if gate["confidence"] < min_confidence:
        return "human_review"
    return "deep_analysis" if gate["condition_met"] else "no_match"


def review_request(*, request_id: str, goal: str, camera_id: str, frame_seq: int,
                   confidence: float) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "decision_type": "cctv_uncertain_condition",
        "interaction_kind": "approval",
        "blocking": True,
        "status": "pending",
        "camera_id": camera_id,
        "frame_seq": frame_seq,
        "summary": f"The check of frame {frame_seq} was uncertain (confidence {confidence:.0%}).",
        "prompt": f"Approve a closer analysis of this snapshot for: {goal}?",
        "options": [
            {"label": "Approve", "description": "Analyze this frame in detail and explain the visible evidence."},
            {"label": "Reject", "description": "Skip detailed analysis of this frame and keep monitoring."},
        ],
        "context": [
            {"label": "Camera", "value": camera_id},
            {"label": "Frame", "value": str(frame_seq)},
            {"label": "Snapshot", "value": "See the image attached to this request."},
        ],
    }


def approved(response: Mapping[str, Any]) -> bool:
    nested = response.get("response")
    value = nested if isinstance(nested, Mapping) else response
    return value.get("approved") is True or str(value.get("decision") or "").lower() in {"approve", "approved"}
