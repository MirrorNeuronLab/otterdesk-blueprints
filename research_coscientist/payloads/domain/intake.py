"""Deterministic research-problem framing."""

from __future__ import annotations

from typing import Any

from mn_autonomous_research_skill import create_research_goal

from .state import _inputs, _save

def frame_goal(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    inputs = _inputs(ctx)
    goal = create_research_goal(
        inputs.get("research_goal") or "Investigate the supplied research question",
        question=inputs.get("research_question") or "",
        success_criteria=list(inputs.get("success_criteria") or []),
        constraints=inputs.get("constraints") or {},
    )
    state = {"inputs": inputs, "goal": goal}
    _save(ctx, state)
    return {"goal": goal}
