"""Purchase decision-packet composition and durable customer outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import (
    BLOCKED_ACTIONS,
    BLUEPRINT_ID,
    BLUEPRINT_NAME,
    CATEGORY,
    DEFAULT_OUTPUT_FOLDER,
    OUTPUT_TYPE,
    RECOMMENDATIONS,
)
from .inputs import expand_runtime_path
from .state import _inputs, _save, _state


def build_final_artifact(inputs: dict[str, Any], evidence: dict[str, Any], recommendation: dict[str, Any], rag: dict[str, Any], sources: list[dict[str, Any]], warnings: list[dict[str, Any]], documents: list[dict[str, Any]], actor_findings: dict[str, Any], run_id: str, intake_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    source_refs = list(dict.fromkeys(["inputs.json", "events.jsonl", "result.json", *(evidence.get("source_refs") or []), *(rag.get("citations") or []), *(item.get("source_ref") for item in sources if item.get("source_ref"))]))
    return {
        "type": OUTPUT_TYPE,
        "schema_version": "mn.blueprint.purchase_research.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "review_ready",
        "purchase_type": inputs.get("purchase_type"),
        "item_description": inputs.get("item_description"),
        "executive_summary": f"Research packet for {inputs.get('purchase_type')} purchase: {inputs.get('item_description') or 'unspecified item'}. Recommendation: {recommendation.get('label')} with {recommendation.get('confidence')} confidence.",
        "recommended_action": recommendation.get("label"),
        "confidence": recommendation.get("confidence"),
        "recommendation_rationale": recommendation.get("rationale"),
        "intake_plan": intake_plan or {},
        "evidence": {"deterministic": evidence, "documents": [{key: value for key, value in item.items() if key != "text"} for item in documents], "public_sources": sources},
        "risk_flags": recommendation.get("risk_flags") or [],
        "evidence_gaps": recommendation.get("evidence_gaps") or [],
        "knowledge_rag": {key: value for key, value in rag.items() if key not in {"_rag_config"}},
        "actor_findings": actor_findings,
        "warnings": warnings,
        "next_steps": ["Review the cited evidence and fill the listed evidence gaps.", "Verify volatile price, availability, policy, and fee facts immediately before acting."],
        "source_refs": source_refs,
        "review_boundary": {"review_required": True, "blocked_actions": BLOCKED_ACTIONS, "reason": "The assistant provides decision support only and does not perform purchase or booking actions."},
    }


def write_user_outputs(final_artifact: dict[str, Any], result: dict[str, Any], config: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, str]]:
    output_dir = resolve_output_folder(config, inputs)
    if output_dir is None:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    quality = build_artifact_quality(final_artifact)
    health = {"schema_version": "mn.blueprint.run_health.v1", "status": "completed_with_warnings" if final_artifact.get("warnings") else "completed", "warning_count": len(final_artifact.get("warnings") or []), "llm": result.get("llm", {})}
    ledger = [
        {"step": "purchase_intake", "status": "completed", "purchase_type": final_artifact.get("purchase_type")},
        {"step": "evidence_and_rag_review", "status": "completed", "source_refs": final_artifact.get("source_refs", [])},
        {"step": "public_research", "status": "completed", "source_count": len((final_artifact.get("evidence") or {}).get("public_sources") or [])},
        {"step": "recommendation", "status": "completed", "label": final_artifact.get("recommended_action"), "confidence": final_artifact.get("confidence")},
        {"step": "human_review_gate", "status": "blocked_pending_review", "blocked_actions": BLOCKED_ACTIONS},
    ]
    final_artifact["artifact_quality"] = quality
    final_artifact["run_health"] = health
    final_artifact["action_ledger"] = ledger
    evidence = final_artifact.get("evidence") or {}
    paths = {
        "purchase_research_json": output_dir / "purchase_research.json",
        "report_markdown": output_dir / "purchase_research_report.md",
        "evidence_json": output_dir / "evidence.json",
        "research_sources_json": output_dir / "research_sources.json",
        "knowledge_rag_json": output_dir / "knowledge_rag.json",
        "action_ledger_json": output_dir / "action_ledger.json",
        "artifact_quality_json": output_dir / "artifact_quality.json",
        "run_health_json": output_dir / "run_health.json",
    }
    output_files = [{"kind": kind, "path": str(path)} for kind, path in paths.items()]
    final_artifact["output_files"] = output_files
    paths["purchase_research_json"].write_text(json.dumps(final_artifact, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["report_markdown"].write_text(render_markdown(final_artifact), encoding="utf-8")
    paths["evidence_json"].write_text(json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["research_sources_json"].write_text(json.dumps(evidence.get("public_sources") or [], indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["knowledge_rag_json"].write_text(json.dumps(final_artifact.get("knowledge_rag") or {}, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["action_ledger_json"].write_text(json.dumps(ledger, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["artifact_quality_json"].write_text(json.dumps(quality, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    paths["run_health_json"].write_text(json.dumps(health, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return output_files


def resolve_output_folder(config: dict[str, Any], inputs: dict[str, Any]) -> Path | None:
    runtime_output_folder = os.environ.get("MN_JOB_OUTPUT_DIR")
    if runtime_output_folder:
        return expand_runtime_path(runtime_output_folder)
    value = inputs.get("output_folder") or (config.get("outputs") or {}).get("folder_path") or DEFAULT_OUTPUT_FOLDER
    value = str(value).strip()
    if not value:
        return None
    return expand_runtime_path(value)


def build_artifact_quality(final_artifact: dict[str, Any]) -> dict[str, Any]:
    checks = [
        {"name": "recommendation_label_valid", "passed": final_artifact.get("recommended_action") in RECOMMENDATIONS},
        {"name": "source_refs_present", "passed": bool(final_artifact.get("source_refs"))},
        {"name": "review_boundary_present", "passed": bool(final_artifact.get("review_boundary"))},
        {"name": "evidence_gaps_explicit", "passed": isinstance(final_artifact.get("evidence_gaps"), list)},
    ]
    passed = all(item["passed"] for item in checks)
    return {"schema_version": "mn.blueprint.artifact_quality.v1", "status": "usable_with_review" if passed else "usable_with_review_warnings", "review_required": True, "quality_checks": checks, "warnings": final_artifact.get("warnings") or []}


def render_markdown(artifact: dict[str, Any]) -> str:
    evidence = artifact.get("evidence") or {}
    intake_plan = artifact.get("intake_plan") or {}
    lines = [
        "# Purchase Research Report",
        "",
        f"**Purchase type:** {artifact.get('purchase_type')}",
        f"**Item or trip:** {artifact.get('item_description') or 'Not specified'}",
        f"**Recommendation:** {artifact.get('recommended_action')}",
        f"**Confidence:** {artifact.get('confidence')}",
        "",
        "## Executive Summary",
        str(artifact.get("executive_summary") or ""),
        "",
        "## Rationale",
        str(artifact.get("recommendation_rationale") or ""),
        "",
        "## Purchase Decision Frame",
        f"- Goal: {intake_plan.get('normalized_goal') or 'Not specified'}",
        f"- Criteria: {', '.join(intake_plan.get('decision_criteria') or []) or 'Not specified'}",
        f"- Unknowns: {', '.join(intake_plan.get('unknowns') or []) or 'None recorded.'}",
        "",
        "## Deterministic Evidence",
        f"- Documents reviewed: {evidence.get('deterministic', {}).get('document_count', 0)}",
        f"- Public sources observed: {evidence.get('deterministic', {}).get('public_source_count', 0)}",
        f"- Observed prices: {evidence.get('deterministic', {}).get('observed_price_values') or 'Unknown'}",
        "",
        "## Risk Flags",
    ]
    lines.extend(f"- {item}" for item in artifact.get("risk_flags") or ["None recorded by deterministic checks."])
    lines.extend(["", "## Evidence Gaps"])
    lines.extend(f"- {item}" for item in artifact.get("evidence_gaps") or ["None recorded."])
    lines.extend(["", "## Sources"])
    lines.extend(f"- `{item}`" for item in artifact.get("source_refs") or ["No source references recorded."])
    lines.extend(["", "## Next Steps"])
    lines.extend(f"- {item}" for item in artifact.get("next_steps") or [])
    lines.extend(["", "## Review Boundary"])
    lines.extend(f"- Do not: {item}" for item in (artifact.get("review_boundary") or {}).get("blocked_actions") or BLOCKED_ACTIONS)
    lines.append("")
    return "\n".join(lines)


def publish_report(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    warnings = [*(state.get("document_warnings") or []), *((state.get("rag") or {}).get("warnings") or []), *(state.get("web_warnings") or [])]
    final = build_final_artifact(inputs, state.get("evidence") or {}, state.get("recommendation") or {}, state.get("rag") or {}, state.get("sources") or [], warnings, state.get("documents") or [], state.get("actor_findings") or {}, ctx["run_id"], intake_plan=state.get("intake_plan") or {})
    final["candidate_comparisons"] = state.get("candidate_comparisons") or []
    final["preferred_candidate"] = (state.get("recommendation") or {}).get("preferred_candidate")
    result = {
        "identity": {"blueprint_id": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run_id": ctx["run_id"]},
        "blueprint": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "category": CATEGORY,
        "run": {"run_id": ctx["run_id"], "status": "completed"}, "inputs": inputs,
        "intake_plan": state.get("intake_plan") or {}, "knowledge_rag": state.get("rag") or {},
        "research_sources": state.get("sources") or [], "evidence": state.get("evidence") or {},
        "recommendation": state.get("recommendation") or {}, "final_artifact": final,
        "llm": state.get("llm_usage") or {},
    }
    final["llm_usage"] = result["llm"]
    output_files = write_user_outputs(final, result, ctx["config"], inputs)
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
    return {"final_artifact": final, "output_files": output_files}


__all__ = [
    "build_artifact_quality",
    "build_final_artifact",
    "publish_report",
    "render_markdown",
    "resolve_output_folder",
    "write_user_outputs",
]
