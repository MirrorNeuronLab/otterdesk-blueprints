"""Research packet verification, composition, and durable customer outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .autonomous import _experiment_concepts
from .common import BLOCKED_ACTIONS, BLUEPRINT_ID, BLUEPRINT_NAME, OUTPUT_TYPE, RESEARCH_ACTIONS
from .evidence import _status_counts, resolve_output_folder
from .state import _inputs, _save, _state


def build_research_packet(
    inputs: dict[str, Any],
    evidence: dict[str, Any],
    recommendation: dict[str, Any],
    rag: dict[str, Any],
    sources: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    actor_findings: dict[str, Any],
    autonomous: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    hypotheses = recommendation["candidate_hypotheses"]
    usable_evidence = bool(evidence.get("usable_evidence_present"))
    status = "review_ready" if usable_evidence else "needs_evidence"
    recommended_action = recommendation["recommended_action"] if usable_evidence else "gather_more_evidence"
    confidence = recommendation["confidence"] if usable_evidence else "low"
    recommendation_rationale = (
        recommendation["rationale"]
        if usable_evidence
        else "No extracted local document or observed public source is available for review."
    )
    source_refs = list(dict.fromkeys(evidence.get("source_refs") or []))
    next_steps = [
        "Review the evidence ledger and resolve the highest-impact gaps.",
        "Ask a qualified reviewer to validate the ranked hypotheses and experiment concepts.",
        "Obtain required safety, ethics, operational, or institutional approvals before any real-world action.",
    ]
    if not usable_evidence:
        next_steps = []
        if not evidence.get("usable_local_document_count"):
            next_steps.append("Provide an approved local paper, note, dataset, or measurement with usable text.")
        if not evidence.get("usable_public_source_count"):
            next_steps.append("Retry public retrieval or provide approved local evidence; no observed public source is available.")
        next_steps.append("Do not use the candidate hypotheses as an evidence-based recommendation until usable evidence is available.")
    return {
        "type": OUTPUT_TYPE,
        "schema_version": "mn.blueprint.research_coscientist.v2",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": status,
        "research_goal": inputs.get("research_goal"),
        "research_domain": inputs.get("research_domain"),
        "research_question": inputs.get("research_question"),
        "scope": inputs.get("scope"),
        "executive_summary": f"Research packet for: {inputs.get('research_goal') or 'unspecified research goal'}. Status: {status}. Posture: {recommended_action} with {confidence} confidence.",
        "recommended_action": recommended_action,
        "confidence": confidence,
        "recommendation_rationale": recommendation_rationale,
        "evidence": {
            "deterministic": evidence,
            "documents": [{key: value for key, value in item.items() if key != "text"} for item in documents],
            "public_sources": sources,
        },
        "hypothesis_ledger": hypotheses,
        "adversarial_review": {
            "required_for_each_hypothesis": ["counterargument", "disconfirming_observation"],
            "actor_findings": actor_findings,
        },
        "autonomous_research": autonomous,
        "experiment_concepts": _experiment_concepts(hypotheses, inputs),
        "knowledge_rag": {key: value for key, value in rag.items() if key not in {"_rag_config", "context"}},
        "evidence_gaps": evidence.get("evidence_gaps") or [],
        "warnings": warnings,
        "next_steps": next_steps,
        "source_refs": source_refs,
        "provenance_refs": ["inputs.json", "events.jsonl", "result.json"],
        "review_boundary": {
            "review_required": True,
            "blocked_actions": BLOCKED_ACTIONS,
            "reason": "Generated hypotheses and plans are decision support only; they are not validated results or authorization for research activity.",
        },
    }


def research_artifact_quality(packet: dict[str, Any]) -> dict[str, Any]:
    deterministic = (packet.get("evidence") or {}).get("deterministic") or {}
    usable_evidence = bool(deterministic.get("usable_evidence_present"))
    expected_status = "review_ready" if usable_evidence else "needs_evidence"
    checks = [
        {"name": "research_action_valid", "passed": packet.get("recommended_action") in RESEARCH_ACTIONS},
        {"name": "usable_evidence_present", "passed": usable_evidence},
        {"name": "packet_status_matches_evidence", "passed": packet.get("status") == expected_status},
        {"name": "hypotheses_labeled", "passed": all(item.get("status") == "hypothesis_for_review" for item in packet.get("hypothesis_ledger") or [])},
        {"name": "review_boundary_present", "passed": bool(packet.get("review_boundary"))},
        {"name": "autonomous_isolation_declared", "passed": (packet.get("autonomous_research") or {}).get("isolation_required") is True},
        {"name": "autonomous_trace_present", "passed": bool(((packet.get("autonomous_research") or {}).get("session") or {}).get("trace"))},
    ]
    return {
        "schema_version": "mn.blueprint.artifact_quality.v1",
        "status": "needs_evidence" if not usable_evidence else ("usable_with_review" if all(item["passed"] for item in checks) else "usable_with_review_warnings"),
        "review_required": True,
        "quality_checks": checks,
        "warnings": packet.get("warnings") or [],
    }


def render_research_markdown(packet: dict[str, Any]) -> str:
    deterministic = (packet.get("evidence") or {}).get("deterministic") or {}
    lines = [
        "# Research Co-Scientist Brief",
        "",
        f"**Research goal:** {packet.get('research_goal') or 'Not specified'}",
        f"**Domain:** {packet.get('research_domain') or 'General'}",
        f"**Status:** {packet.get('status')}",
        f"**Review posture:** {packet.get('recommended_action')}",
        f"**Confidence:** {packet.get('confidence')}",
        "",
        "## Executive Summary",
        str(packet.get("executive_summary") or ""),
        "",
        "## Evidence Coverage",
        f"- Local documents reviewed: {deterministic.get('document_count', 0)}",
        f"- Public sources observed: {deterministic.get('public_source_count', 0)}",
        f"- Usable evidence present: {'Yes' if deterministic.get('usable_evidence_present') else 'No'}",
        "",
        "## Candidate Hypotheses",
    ]
    for hypothesis in packet.get("hypothesis_ledger") or []:
        lines.extend([
            f"### {hypothesis.get('hypothesis_id')}: {hypothesis.get('statement')}",
            f"- Prediction: {hypothesis.get('prediction')}",
            f"- Counterargument: {hypothesis.get('counterargument')}",
            f"- Disconfirming observation: {hypothesis.get('disconfirming_observation')}",
        ])
    lines.extend(["", "## Evidence Gaps"])
    lines.extend(f"- {gap}" for gap in packet.get("evidence_gaps") or ["No gaps recorded."])
    lines.extend(["", "## Next Steps"])
    lines.extend(f"- {step}" for step in packet.get("next_steps") or [])
    lines.extend(["", "## Review Boundary"])
    lines.extend(f"- Do not: {action}" for action in (packet.get("review_boundary") or {}).get("blocked_actions") or BLOCKED_ACTIONS)
    lines.append("")
    return "\n".join(lines)


def write_research_outputs(
    packet: dict[str, Any], result: dict[str, Any], config: dict[str, Any], inputs: dict[str, Any]
) -> list[dict[str, str]]:
    output_dir = resolve_output_folder(config, inputs)
    if output_dir is None:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    quality = research_artifact_quality(packet)
    health = {
        "schema_version": "mn.blueprint.run_health.v1",
        "status": "completed_with_warnings" if packet.get("warnings") else "completed",
        "warning_count": len(packet.get("warnings") or []),
        "llm": result.get("llm", {}),
    }
    review_ledger = [
        {"stage": "goal_framing", "status": "completed"},
        {"stage": "evidence_evaluation", "status": "completed", "source_refs": packet.get("source_refs", [])},
        {"stage": "hypothesis_and_adversarial_review", "status": "completed", "hypothesis_count": len(packet.get("hypothesis_ledger") or [])},
        {"stage": "human_review_gate", "status": "blocked_pending_review", "blocked_actions": BLOCKED_ACTIONS},
    ]
    packet["artifact_quality"] = quality
    packet["run_health"] = health
    packet["review_ledger"] = review_ledger
    paths = {
        "research_packet": output_dir / "research_packet.json",
        "research_brief": output_dir / "research_brief.md",
        "evidence_ledger": output_dir / "evidence_ledger.json",
        "hypothesis_ledger": output_dir / "hypothesis_ledger.json",
        "review_ledger": output_dir / "review_ledger.json",
        "artifact_quality": output_dir / "artifact_quality.json",
        "run_health": output_dir / "run_health.json",
    }
    output_files = [{"kind": kind, "path": str(path)} for kind, path in paths.items()]
    packet["output_files"] = output_files
    paths["research_packet"].write_text(json.dumps(packet, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["research_brief"].write_text(render_research_markdown(packet), encoding="utf-8")
    paths["evidence_ledger"].write_text(json.dumps(packet["evidence"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["hypothesis_ledger"].write_text(json.dumps(packet["hypothesis_ledger"], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["review_ledger"].write_text(json.dumps(review_ledger, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["artifact_quality"].write_text(json.dumps(quality, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["run_health"].write_text(json.dumps(health, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return output_files


def publish_packet(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    autonomous = state.get("autonomous") or {}
    session = autonomous.get("session") if isinstance(autonomous.get("session"), dict) else {}
    if autonomous.get("isolation_required") is not True or not session.get("trace"):
        raise ValueError("autonomous output lacks the required OpenShell isolation and trace contract")
    audit = state.get("packet_audit") or {}
    if audit.get("status") == "needs_revision" and "evidence_references_present" not in set(audit.get("blocking_findings") or []):
        raise ValueError("research packet failed deterministic traceability and falsifiability checks")
    final = build_research_packet(inputs, state.get("evidence") or {}, state.get("recommendation") or {}, state.get("rag") or {}, state.get("sources") or [], state.get("warnings") or [], state.get("documents") or [], state.get("actor_findings") or {}, autonomous, ctx["run_id"])
    final["packet_audit"] = audit
    result = {"identity": {"blueprint_id": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run_id": ctx["run_id"]}, "blueprint": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run": {"run_id": ctx["run_id"], "status": "completed"}, "inputs": inputs, "evidence": state.get("evidence") or {}, "autonomous_research": autonomous, "final_artifact": final, "llm": state.get("llm_usage") or {}}
    final["llm_usage"] = result["llm"]
    output_files = write_research_outputs(final, result, ctx["config"], inputs)
    result["output_files"] = output_files
    run_dir = Path(ctx["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "final_artifact.json").write_text(
        json.dumps(final, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    _save(ctx, state)
    return {"final_artifact": final, "output_files": output_files, "artifact_quality": research_artifact_quality(final)}


__all__ = [
    "build_research_packet",
    "publish_packet",
    "render_research_markdown",
    "research_artifact_quality",
    "write_research_outputs",
]
