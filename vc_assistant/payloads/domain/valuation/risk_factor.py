"""risk factor valuation strategy."""

from __future__ import annotations

from typing import Any

from ..research_policy import method_result

def score_risk_factor_summation(facts: dict[str, Any]) -> dict[str, Any]:
    risk_factors = [
        "management",
        "stage",
        "legislation",
        "manufacturing",
        "sales",
        "funding",
        "competition",
        "technology",
        "litigation",
        "international",
        "reputation",
        "exit",
    ]
    text_terms = set(facts["risk_facts"]["warning_terms"])
    adjustments = {
        factor: {
            "adjustment": -1 if factor in text_terms else 0,
            "status": "scored" if factor in text_terms else "insufficient_evidence",
        }
        for factor in risk_factors
    }
    status = "scored" if facts["risk_facts"]["score"] else "insufficient_evidence"
    return method_result(
        method_id="risk_factor_summation_method",
        memory_hook="12-risk checklist",
        status=status,
        score=max(0, 100 - facts["risk_facts"]["score"]) if status == "scored" else None,
        inputs_used=risk_factors,
        formula_or_weighting="100 - keyword_risk_score; adjustment table records observed risk factors",
        assumptions=["Risk adjustments are directional diligence prompts, not price adjustments."],
        source_refs=facts["team_facts"]["evidence_refs"],
        warnings=["Several risk checklist factors lack explicit evidence."] if status == "scored" else ["No explicit risk evidence found."],
        details={"risk_adjustments": adjustments},
    )
