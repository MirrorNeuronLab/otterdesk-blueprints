"""first chicago valuation strategy."""

from __future__ import annotations

from typing import Any

from ..research_policy import method_result

def score_first_chicago(facts: dict[str, Any]) -> dict[str, Any]:
    has_values = bool(facts["financial_facts"]["local_monetary_values"] or facts["financial_facts"]["public_monetary_values"] or facts["financial_facts"]["tool_monetary_values"])
    status = "scored" if has_values and facts["traction_facts"]["score"] >= 15 else "insufficient_evidence"
    cases = {
        "bear": {"probability": 0.35, "score": max(0, facts["traction_facts"]["score"] - 25)},
        "base": {"probability": 0.45, "score": round((facts["traction_facts"]["score"] + facts["market_facts"]["score"]) / 2, 2)},
        "bull": {"probability": 0.20, "score": min(100, max(facts["traction_facts"]["score"], facts["market_facts"]["score"]) + 20)},
    }
    weighted = sum(case["probability"] * case["score"] for case in cases.values()) if status == "scored" else None
    return method_result(
        method_id="first_chicago_method",
        memory_hook="Bear/base/bull cases",
        status=status,
        score=weighted,
        inputs_used=["traction_score", "market_score", "local_monetary_values"],
        formula_or_weighting="0.35 * bear + 0.45 * base + 0.20 * bull",
        assumptions=["Scenario probabilities are defaults and should be adjusted by investment committee policy."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["market_facts"]["public_source_refs"][:5],
        warnings=[] if status == "scored" else ["Scenario math needs both traction and monetary evidence."],
        details={"cases": cases},
        missing_evidence=[] if status == "scored" else ["First Chicago needs monetary evidence plus traction evidence before scenario math is useful."],
    )
