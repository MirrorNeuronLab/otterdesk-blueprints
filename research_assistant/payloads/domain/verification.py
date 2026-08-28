"""Deterministic audit of autonomous research output before publication."""

from __future__ import annotations

from typing import Any

from .autonomous import _experiment_concepts
from .state import _save, _state


def audit_packet(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    autonomous = state.get("autonomous") or {}
    session = autonomous.get("session") if isinstance(autonomous.get("session"), dict) else {}
    hypotheses = (state.get("recommendation") or {}).get("candidate_hypotheses") or []
    inputs = state.get("inputs") or {}
    experiments = _experiment_concepts(hypotheses, inputs)
    valid_refs = set((state.get("evidence") or {}).get("source_refs") or [])
    generic_prediction_markers = ("pre-specified measurement", "measurement differs from baseline")
    phase_names = {
        str(item.get("phase") or "")
        for item in autonomous.get("research_phase_trace") or []
        if isinstance(item, dict)
    }
    required_phases = {
        "source_analysis",
        "question_decomposition",
        "competing_hypothesis_generation",
        "gap_and_probe_planning",
        "evidence_and_probe_revision",
        "experiment_design",
        "meta_review_and_ranking",
        "executive_synthesis",
    }
    usage = state.get("llm_usage") if isinstance(state.get("llm_usage"), dict) else {}
    checks = [
        {
            "name": "isolated_autonomous_trace",
            "passed": autonomous.get("isolation_required") is True
            and autonomous.get("runner") == "docker_worker"
            and bool(session.get("trace")),
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
            "name": "deep_research_phases_complete",
            "passed": required_phases <= phase_names
            and any(name.startswith("adversarial_review_") for name in phase_names),
        },
        {
            "name": "source_analysis_present",
            "passed": bool((autonomous.get("source_analysis") or {}).get("source_assessments")),
        },
        {
            "name": "live_model_backed_when_required",
            "passed": not autonomous.get("live_model_required")
            or (
                int(usage.get("calls") or 0) >= len(phase_names)
                and int(usage.get("fallback_calls") or 0) == 0
            ),
        },
        {
            "name": "evidence_references_present",
            "passed": bool((state.get("evidence") or {}).get("source_refs")),
        },
        {
            "name": "hypothesis_source_refs_valid",
            "passed": bool(hypotheses)
            and all(
                item.get("evidence_support")
                and set(item.get("evidence_support") or []) <= valid_refs
                for item in hypotheses
            ),
        },
        {
            "name": "hypothesis_predictions_specific",
            "passed": bool(hypotheses)
            and all(
                item.get("prediction")
                and not any(
                    marker in str(item.get("prediction") or "").lower()
                    for marker in generic_prediction_markers
                )
                for item in hypotheses
            ),
        },
        {
            "name": "experiment_procedures_complete",
            "passed": len(experiments) == len(hypotheses)
            and bool(experiments)
            and all(
                item.get("unit_of_analysis")
                and item.get("primary_outcome")
                and len(item.get("procedure") or []) >= 4
                and item.get("decision_rule")
                and item.get("analysis_plan")
                and item.get("stop_conditions")
                for item in experiments
            ),
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
