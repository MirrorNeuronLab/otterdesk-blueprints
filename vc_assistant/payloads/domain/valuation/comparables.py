"""comparables valuation strategy."""

from __future__ import annotations

from typing import Any

from ..research_policy import method_result

def score_comparables(facts: dict[str, Any]) -> dict[str, Any]:
    source_count = facts["comparable_candidates"]["source_count"]
    status = "scored" if source_count else "insufficient_evidence"
    return method_result(
        method_id="comparables_market_multiple_method",
        memory_hook="What are similar companies worth?",
        status=status,
        score=(facts["market_facts"]["score"] + facts["traction_facts"]["score"]) / 2 if status == "scored" else None,
        inputs_used=["market_score", "traction_score", "public_source_count", "comparable_domains"],
        formula_or_weighting="average(market_score, traction_score) when public comparable evidence exists",
        assumptions=["Public comparable snippets are screening evidence; no private transaction database is assumed."],
        source_refs=facts["comparable_candidates"]["public_source_refs"],
        warnings=[] if status == "scored" else ["No substantive public comparable evidence found."],
        details={"source_count": source_count, "domains": facts["comparable_candidates"]["domains"][:12], "financial_tool_outputs": facts["financial_facts"]["financial_tool_outputs"]},
        missing_evidence=[] if status == "scored" else ["No substantive public comparable source or deterministic financial-tool comparable was available."],
    )
