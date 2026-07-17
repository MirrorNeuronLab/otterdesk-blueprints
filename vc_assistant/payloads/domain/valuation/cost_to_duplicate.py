"""cost to duplicate valuation strategy."""

from __future__ import annotations

from typing import Any

from ..common import evidence_status
from ..research_policy import method_result

def score_cost_to_duplicate(facts: dict[str, Any]) -> dict[str, Any]:
    status = evidence_status(facts["ip_asset_facts"]["score"])
    return method_result(
        method_id="cost_to_duplicate_method",
        memory_hook="What would it cost to rebuild?",
        status=status,
        score=facts["ip_asset_facts"]["score"] if status == "scored" else None,
        inputs_used=["ip_asset_score", "product_score", "asset_keywords"],
        formula_or_weighting="asset keyword evidence score across built, patent, R&D, dataset, hardware, model, and infrastructure terms",
        assumptions=["Cost-to-duplicate is a floor proxy and misses upside."],
        source_refs=facts["team_facts"]["evidence_refs"],
        warnings=[] if status == "scored" else ["No rebuild-cost asset evidence found."],
        details={"evidence_terms": facts["ip_asset_facts"]["keywords"]},
    )
