"""berkus valuation strategy."""

from __future__ import annotations

from typing import Any

from ..research_policy import method_result

def score_berkus(facts: dict[str, Any]) -> dict[str, Any]:
    buckets = {
        "sound_idea": facts["market_facts"]["score"],
        "prototype": facts["product_facts"]["score"],
        "quality_management_team": facts["team_facts"]["score"],
        "strategic_relationships": facts["relationship_facts"]["score"],
        "product_rollout_or_sales": facts["traction_facts"]["score"],
    }
    status = "scored" if any(buckets.values()) else "insufficient_evidence"
    return method_result(
        method_id="berkus_method",
        memory_hook="5 buckets",
        status=status,
        score=sum(buckets.values()) / len(buckets) if status == "scored" else None,
        inputs_used=list(buckets),
        formula_or_weighting="average(sound_idea, prototype, team, strategic_relationships, rollout_or_sales)",
        assumptions=["Bucket scores are 0-100 evidence-strength indicators, not a valuation."],
        source_refs=facts["team_facts"]["evidence_refs"] + facts["market_facts"]["public_source_refs"][:5],
        details={"buckets": buckets},
    )
