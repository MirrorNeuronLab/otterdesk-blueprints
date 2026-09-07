"""Run the agent only after validated deterministic ingestion."""

from pathlib import Path
from mn_sdk.step_runtime import artifact_reference
from mn_sdk.blueprint_support import source_manifest
from mn_prototype_bounded_tool_loop_agent.checkpoint import atomic_json
from .indexing import validate_indexes
from .app.agentic import run_investigation
from .app.review import build_review


def investigate(context, *, llm_client=None):
    case = Path(context["run_dir"]) / "case"
    corpus, receipt = validate_indexes(
        case, context["config"]["investigation"]["access_scope"]
    )
    state, store = run_investigation(
        case,
        corpus,
        receipt,
        context,
        llm_client,
        declared=[d["name"] for d in source_manifest(__file__)["skill_dependencies"]],
    )
    summary = build_review(state, store, context["payload"]["goal"])
    atomic_json(case / "investigation.json", summary)
    refs = [
        artifact_reference(key, "case/" + path)
        for key, path in (
            ("investigation", "investigation.json"),
            ("evidence_database", "evidence.sqlite3"),
            ("agent_checkpoint", "agent_checkpoint.json"),
            ("evidence_graph", "evidence.rgx"),
        )
    ]
    return {
        "investigation": refs[0],
        "audit_database": refs[1],
        "stop_reason": state["stop_reason"],
    }, refs
