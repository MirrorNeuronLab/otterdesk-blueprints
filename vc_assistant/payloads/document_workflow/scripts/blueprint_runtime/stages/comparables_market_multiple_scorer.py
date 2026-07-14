from __future__ import annotations

from typing import Any

from .scoring_stage import run_scorer_step


def run_comparables_market_multiple_scorer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    return run_scorer_step(ctx, "comparables_market_multiple_scorer", llm_client=llm_client)
