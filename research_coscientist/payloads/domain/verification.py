"""Deterministic audit of autonomous research output before publication."""

from __future__ import annotations

from typing import Any

from .state import _save, _state


def audit_packet(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    autonomous = state.get("autonomous") or {}
    session = autonomous.get("session") if isinstance(autonomous.get("session"), dict) else {}
    hypotheses = (state.get("recommendation") or {}).get("candidate_hypotheses") or []
    checks = [
        {
            "name": "isolated_autonomous_trace",
            "passed": autonomous.get("isolation_required") is True and bool(session.get("trace")),
        },
        {
            "name": "hypotheses_are_falsifiable",
            "passed": bool(hypotheses)
            and all(item.get("prediction") and item.get("disconfirming_observation") for item in hypotheses),
        },
        {
            "name": "hypotheses_preserve_counterarguments",
            "passed": bool(hypotheses) and all(item.get("counterargument") for item in hypotheses),
        },
        {
            "name": "evidence_references_present",
            "passed": bool((state.get("evidence") or {}).get("source_refs")),
        },
    ]
    audit = {
        "status": "passed" if all(item["passed"] for item in checks) else "needs_revision",
        "checks": checks,
        "blocking_findings": [item["name"] for item in checks if not item["passed"]],
        "review_required": True,
    }
    state["packet_audit"] = audit
    _save(ctx, state)
    return audit
