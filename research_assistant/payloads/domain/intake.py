"""Deterministic research-problem framing."""

from __future__ import annotations

from mn_sdk.integrations.block_inputs import save_declared_inputs
from mn_sdk.agent_events import report_activity

from typing import Any

from mn_autonomous_research_skill import create_research_goal

from .state import research_inputs, save_state
from .common import BLUEPRINT_ID

def frame_goal(block, inputs) -> dict[str, Any]:
    report_activity("Clarifying the research goal", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    inputs = research_inputs(block, inputs)
    goal = create_research_goal(
        inputs.get("research_goal") or "Investigate the supplied research question",
        question=inputs.get("research_question") or "",
        success_criteria=list(inputs.get("success_criteria") or []),
        constraints=inputs.get("constraints") or {},
    )
    state = {"inputs": inputs, "goal": goal,
        "input_artifact": save_declared_inputs(block, inputs, runtime_file=__file__).to_dict()}
    return {"goal": goal, "state": save_state(block, state, "goal")}
