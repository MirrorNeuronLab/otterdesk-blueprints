"""Research Co-Scientist domain operations and durable research state."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mn_blueprint_support import get_actor_llm_client, resolve_actor_specs, run_actor_reviews
from mn_sdk.blueprint_support import WorkflowStateStore

from . import workflow


STATE_FILE = "research_coscientist_state.json"


def _inputs(ctx: dict[str, Any]) -> dict[str, Any]:
    return workflow.normalize_inputs({**((ctx["config"].get("inputs") or {}).get("payload") or {}), **ctx["payload"]})


def _state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def _save(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)


def frame_goal(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    inputs = _inputs(ctx)
    goal = workflow.create_research_goal(
        inputs.get("research_goal") or "Investigate the supplied research question",
        question=inputs.get("research_question") or "",
        success_criteria=list(inputs.get("success_criteria") or []),
        constraints=inputs.get("constraints") or {},
    )
    state = {"inputs": inputs, "goal": goal}
    _save(ctx, state)
    return {"goal": goal}


def prepare_evidence(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    llm_mode = str((ctx["config"].get("llm") or {}).get("mode") or "live")
    prepared = workflow.prepare_evidence_context(
        ctx["config"], inputs, Path(ctx["blueprint_dir"]), ctx["run_id"],
        quick_test=llm_mode in {"fake", "mock"} or bool((ctx["config"].get("execution") or {}).get("quick_test")),
    )
    state.update({"inputs": inputs, "documents": prepared["documents"], "rag": prepared["rag"], "sources": prepared["sources"], "evidence": prepared["evidence"], "posture": workflow.deterministic_research_posture(prepared["evidence"]), "warnings": prepared["warnings"]})
    _save(ctx, state)
    return {"source_count": len(prepared["sources"]), "document_count": len(prepared["documents"])}


def autonomous_research(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    llm = get_actor_llm_client(ctx["config"], None)
    documents = state.get("documents") or []
    sources = state.get("sources") or []
    evidence = state.get("evidence") or workflow.research_evidence(inputs, documents, sources)
    posture = state.get("posture") or workflow.deterministic_research_posture(evidence)
    recommendation, autonomous, autonomous_warnings = workflow.run_autonomous_research(
        llm, inputs, evidence, state.get("rag") or {}, posture, ctx["config"], documents, sources,
        workspace=Path(os.environ.get("MN_WORKDIR") or Path(ctx["run_dir"]) / "workspace"),
    )
    verified_evidence = workflow.research_evidence(inputs, documents, sources)
    actor_findings = run_actor_reviews(
        config=ctx["config"], llm=llm, actor_ids=list(resolve_actor_specs(ctx["config"]).keys()), state={},
        task=workflow.load_prompt("research-review-task.md"),
        context={"inputs": inputs, "evidence": verified_evidence, "recommendation": recommendation, "rag": state.get("rag") or {}, "sources": sources},
    )
    state.update({"inputs": inputs, "evidence": verified_evidence, "posture": workflow.deterministic_research_posture(verified_evidence), "recommendation": recommendation, "autonomous": autonomous, "actor_findings": actor_findings, "warnings": [*(state.get("warnings") or []), *autonomous_warnings], "llm_usage": workflow.llm_usage(llm)})
    _save(ctx, state)
    return {"tool_calls": (autonomous.get("session") or {}).get("tool_calls_used", 0)}


def publish_packet(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    autonomous = state.get("autonomous") or {}
    session = autonomous.get("session") if isinstance(autonomous.get("session"), dict) else {}
    if autonomous.get("isolation_required") is not True or not session.get("trace"):
        raise ValueError("autonomous output lacks the required OpenShell isolation and trace contract")
    final = workflow.build_research_packet(inputs, state.get("evidence") or {}, state.get("recommendation") or {}, state.get("rag") or {}, state.get("sources") or [], state.get("warnings") or [], state.get("documents") or [], state.get("actor_findings") or {}, autonomous, ctx["run_id"])
    result = {"identity": {"blueprint_id": workflow.BLUEPRINT_ID, "name": workflow.BLUEPRINT_NAME, "run_id": ctx["run_id"]}, "blueprint": workflow.BLUEPRINT_ID, "name": workflow.BLUEPRINT_NAME, "run": {"run_id": ctx["run_id"], "status": "completed"}, "inputs": inputs, "evidence": state.get("evidence") or {}, "autonomous_research": autonomous, "final_artifact": final, "llm": state.get("llm_usage") or {}}
    final["llm_usage"] = result["llm"]
    output_files = workflow.write_research_outputs(final, result, ctx["config"], inputs)
    result["output_files"] = output_files
    _save(ctx, state)
    return {"final_artifact": final, "output_files": output_files, "artifact_quality": workflow.research_artifact_quality(final)}

