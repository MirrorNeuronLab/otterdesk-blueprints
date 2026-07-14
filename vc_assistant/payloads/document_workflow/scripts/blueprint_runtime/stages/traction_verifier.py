from __future__ import annotations

from typing import Any

from .research_stage import run_research_stage_step


def run_traction_verifier_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    return run_research_stage_step(ctx, "traction_verifier", llm_client=llm_client)
