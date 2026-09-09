"""scorecard valuation strategy."""

from __future__ import annotations

from typing import Any

from ..research_policy import method_result

def score_scorecard(facts: dict[str, Any]) -> dict[str, Any]:
    weights = {
        "team": 0.30,
        "market": 0.25,
        "product": 0.15,
        "traction": 0.15,
        "competition": 0.10,
        "financing_need": 0.05,
    }
    factors = {
        "team": facts["team_facts"]["score"],
        "market": facts["market_facts"]["score"],
        "product": facts["product_facts"]["score"],
        "traction": facts["traction_facts"]["score"],
        "competition": max(0, 100 - facts["risk_facts"]["score"]),
        "financing_need": 60 if facts["financial_facts"]["local_monetary_values"] else 25,
    }
    substantive_inputs = [key for key in ("team", "market", "product", "traction") if factors[key] > 0]
    if facts["financial_facts"]["local_monetary_values"]:
        substantive_inputs.append("financing_need")
    status = "scored" if substantive_inputs else "insufficient_evidence"
    return method_result(
        method_id="scorecard_bill_payne_method",
        memory_hook="Compare to the average startup",
        status=status,
        score=sum(factors[key] * weight for key, weight in weights.items()) if status == "scored" else None,
        inputs_used=list(factors),
        formula_or_weighting=weights,
        assumptions=["Weights are default early-stage screening weights and should be calibrated by fund strategy."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["market_facts"]["public_source_refs"][:5],
        warnings=["Competition and financing-need defaults are not sufficient evidence by themselves."] if status == "scored" else ["No substantive Scorecard evidence found."],
        details={
            "factors": factors,
            "substantive_inputs": substantive_inputs,
            "non_substantive_default_inputs": ["competition"] + ([] if facts["financial_facts"]["local_monetary_values"] else ["financing_need"]),
        },
    )
