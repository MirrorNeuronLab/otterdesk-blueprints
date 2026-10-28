"""Deterministic research-problem framing."""

from __future__ import annotations

import json
from jsonschema import validate
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.integrations.block_inputs import save_declared_inputs
from mn_sdk.agent_events import report_activity

from typing import Any

from mn_autonomous_research_skill import create_research_goal

from .state import research_inputs, save_state
from .common import BLUEPRINT_ID

def frame_goal(block, inputs) -> dict[str, Any]:
    report_activity("Clarifying the research goal", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    inputs = research_inputs(block, inputs)
    instructions = inputs.get("supervisor_instructions", [])
    declaration = source_manifest(__file__)["contracts"]["inputs"]["supervisor_instructions"]
    validate(instructions, {key: value for key, value in declaration.items() if key != "required"})
    if len(json.dumps(instructions, ensure_ascii=False, separators=(",", ":")).encode()) > 16000 or len({item["id"] for item in instructions}) != len(instructions):
        raise ValueError("Saved research instructions exceed the supported bounds")
    goal = create_research_goal(
        inputs.get("research_goal") or "Investigate the supplied research question",
        question=inputs.get("research_question") or "",
        success_criteria=list(inputs.get("success_criteria") or []),
        constraints=inputs.get("constraints") or {},
    )
    state = {"inputs": inputs, "goal": goal, "supervisor_instruction_revision": fingerprint(instructions),
        "input_artifact": save_declared_inputs(block, inputs, runtime_file=__file__).to_dict()}
    return {"goal": goal, "state": save_state(block, state, "goal")}
