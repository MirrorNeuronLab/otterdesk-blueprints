"""venture capital valuation strategy."""

from __future__ import annotations

from typing import Any

from ..research_policy import method_result

def score_venture_capital_method(facts: dict[str, Any]) -> dict[str, Any]:
    largest_value = facts["financial_facts"]["largest_relevant_value"]
    assumed_exit_value = largest_value * 8 if largest_value else None
    status = "scored" if assumed_exit_value else "insufficient_evidence"
    score = min(100, facts["traction_facts"]["score"] * 0.6 + facts["market_facts"]["score"] * 0.4) if status == "scored" else None
    return method_result(
        method_id="venture_capital_method",
        memory_hook="Work backward from exit",
        status=status,
        score=score,
        inputs_used=["largest_relevant_monetary_value", "traction_score", "market_score"],
        formula_or_weighting={"assumed_exit_value": "largest_relevant_value * 8", "score": "0.6 * traction + 0.4 * market"},
        assumptions=["Uses the largest extracted local/public/tool monetary figure as a rough proxy only when available.", "Required return multiple defaults to 10x."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["comparable_candidates"]["public_source_refs"][:5],
        warnings=[] if status == "scored" else ["No monetary value found for exit-back math."],
        details={"assumed_exit_value": assumed_exit_value, "required_return_multiple": 10, "monetary_value_source": "local_or_public_or_financial_tool"},
        missing_evidence=[] if status == "scored" else ["No local, public, or financial-tool monetary value was available for exit-back math."],
    )
