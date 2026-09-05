"""Durable publication of the read-only deep architecture evidence bundle."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import BLOCKED_ACTIONS, BLUEPRINT_ID, BLUEPRINT_NAME, OUTPUT_TYPE, expand_output_path
from .prompts import render_prompt_markdown
from .report_views import (
    render_architecture_report,
    render_dependency_analysis,
    render_executive_summary,
    render_hotspots,
    render_migration_plan,
    render_prioritized_findings,
    render_repository_map,
    render_state_model,
    render_system_architecture,
    render_test_architecture,
    render_trust_boundaries,
)
from .state import inputs_for, read_state, write_state


def publish_advice(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = read_state(ctx)
    audit = state.get("audit") or {}
    if audit.get("status") != "passed":
        raise ValueError("Architecture advice failed its evidence and read-only audit.")
    inputs = inputs_for(ctx)
    metrics = state.get("metrics") or {}
    findings = state.get("findings") or []
    prompts = state.get("prompt_pack") or []
    narrative = ((state.get("report_draft") or {}).get("sections") or {})
    llm_analysis = state.get("llm_analysis") or {}
    assessment = {
        "type": OUTPUT_TYPE,
        "schema_version": "mn.blueprint.software_architecture_advisor.v3",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": ctx["run_id"],
        "status": "review_ready",
        "executive_summary": (narrative.get("executive_summary") or {}).get("text") or _summary(metrics, findings),
        "deterministic_summary": _summary(metrics, findings),
        "recommended_action": "review_and_choose_one_improvement_prompt",
        "confidence": _confidence(findings),
        "source_snapshot": _safe_source(state.get("source") or {}),
        "analysis_focus": inputs.get("analysis_focus") or [],
        "evidence": {
            "availability": state.get("evidence_availability") or {},
            "repository_profile": state.get("repository_profile") or {},
            "inventory": state.get("inventory") or {},
            "metrics": metrics,
            "hotspots": state.get("hotspots") or [],
            "state_model": state.get("state_model") or {},
            "trust_model": state.get("trust_model") or {},
            "test_architecture": state.get("test_architecture") or {},
            "deployment_model": state.get("deployment_model") or {},
            "history": state.get("history_evidence") or {},
            "fact_database": state.get("architecture_facts") or {},
            "findings": findings,
        },
        "architecture_reconstruction": state.get("architecture_reconstruction") or {},
        "cross_cutting_analysis": state.get("cross_cutting_analysis") or {},
        "report_narrative": narrative,
        "adversarial_review": state.get("adversarial_review") or {},
        "llm_analysis": llm_analysis,
        "improvement_prompts": [
            {
                key: item.get(key)
                for key in ("prompt_id", "finding_id", "title", "priority", "severity", "confidence", "fact_ids")
            }
            for item in prompts
        ],
        "limitations": [
            "This is bounded static, read-only analysis. Runtime traces, executed tests, compiler semantics, and production ownership remain unavailable unless explicitly staged.",
            "A HIGH recommendation requires at least two static evidence types, but still requires repository and maintainer verification before implementation.",
            "The assessment does not authorize a refactor. Validate every cited fact, path, and counter-evidence check in the current checkout.",
        ],
        "next_steps": [
            "Review evidence availability and reject findings that depend on missing critical context.",
            "Choose one highest-leverage surviving prompt and validate all cited fact IDs.",
            "Have an implementation agent propose and test the smallest reversible change.",
            "Rerun the advisor after implementation to compare structural evidence.",
        ],
        "source_refs": [
            "inputs.json", "source_inventory.json", "architecture_graph.json",
            "evidence/architecture_facts.json", "evidence/llm_analysis.json", "analysis_metrics.json",
        ],
        "provenance_refs": ["inputs.json", "events.jsonl", "llm_trace.jsonl", "result.json"],
        "review_boundary": {
            "read_only": True,
            "blocked_actions": BLOCKED_ACTIONS,
            "network": "forbidden",
            "target_code_executed": False,
        },
        "audit": audit,
    }
    output_dir = expand_output_path(inputs.get("output_folder") or "")
    report_dir = output_dir / "architecture-report"
    evidence_dir = output_dir / "evidence"
    prompt_dir = output_dir / "prompts"
    for directory in (output_dir, report_dir, evidence_dir, prompt_dir):
        directory.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {
        "architecture_assessment": output_dir / "architecture_assessment.json",
        "architecture_report": output_dir / "architecture_report.md",
        "improvement_prompts": output_dir / "improvement_prompts.md",
        "improvement_prompts_json": output_dir / "improvement_prompts.json",
        "prompt_index": prompt_dir / "README.md",
        "architecture_graph": output_dir / "architecture_graph.json",
        "source_inventory": output_dir / "source_inventory.json",
        "analysis_metrics": output_dir / "analysis_metrics.json",
        "repository_profile": evidence_dir / "repository_profile.json",
        "symbol_index": evidence_dir / "symbol_index.json",
        "architecture_facts": evidence_dir / "architecture_facts.json",
        "state_model": evidence_dir / "state_model.json",
        "trust_boundaries": evidence_dir / "trust_boundaries.json",
        "test_architecture": evidence_dir / "test_architecture.json",
        "deployment_model": evidence_dir / "deployment_model.json",
        "history_evidence": evidence_dir / "history_evidence.json",
        "architecture_reconstruction": evidence_dir / "architecture_reconstruction.json",
        "adversarial_review": evidence_dir / "adversarial_review.json",
        "prioritized_findings": evidence_dir / "prioritized_findings.json",
        "llm_analysis": evidence_dir / "llm_analysis.json",
        "llm_trace": output_dir / "llm_trace.jsonl",
        "executive_summary_report": report_dir / "00-executive-summary.md",
        "repository_map_report": report_dir / "01-repository-map.md",
        "system_architecture_report": report_dir / "02-system-architecture.md",
        "state_model_report": report_dir / "04-state-model.md",
        "dependency_report": report_dir / "05-dependency-analysis.md",
        "hotspots_report": report_dir / "06-hotspots.md",
        "trust_report": report_dir / "08-security-boundaries.md",
        "test_report": report_dir / "09-test-architecture.md",
        "findings_report": report_dir / "10-prioritized-findings.md",
        "migration_report": report_dir / "12-migration-plan.md",
    }
    for index, prompt in enumerate(prompts, start=1):
        slug = _slug(prompt.get("title") or prompt.get("prompt_id") or str(index))
        paths[f"codex_prompt_{index}"] = prompt_dir / f"{index:02d}-{slug}.md"

    output_files = [{"kind": kind, "path": str(path)} for kind, path in paths.items()]
    assessment["output_files"] = output_files

    json_values = {
        "architecture_assessment": assessment,
        "improvement_prompts_json": prompts,
        "architecture_graph": state.get("graph") or {},
        "source_inventory": state.get("inventory") or {},
        "analysis_metrics": metrics,
        "repository_profile": state.get("repository_profile") or {},
        "symbol_index": state.get("symbol_index") or {},
        "architecture_facts": state.get("architecture_facts") or {},
        "state_model": state.get("state_model") or {},
        "trust_boundaries": state.get("trust_model") or {},
        "test_architecture": state.get("test_architecture") or {},
        "deployment_model": state.get("deployment_model") or {},
        "history_evidence": state.get("history_evidence") or {},
        "architecture_reconstruction": state.get("architecture_reconstruction") or {},
        "adversarial_review": state.get("adversarial_review") or {},
        "prioritized_findings": {"schema_version": "mn.architecture.findings.v1", "findings": findings},
        "llm_analysis": llm_analysis,
    }
    for kind, value in json_values.items():
        paths[kind].write_text(_json(value), encoding="utf-8")

    markdown_values = {
        "architecture_report": render_architecture_report(assessment),
        "improvement_prompts": render_prompt_markdown(prompts),
        "prompt_index": _render_prompt_index(prompts),
        "executive_summary_report": render_executive_summary(assessment),
        "repository_map_report": render_repository_map(state),
        "system_architecture_report": render_system_architecture(state),
        "state_model_report": render_state_model(state),
        "dependency_report": render_dependency_analysis(state),
        "hotspots_report": render_hotspots(state),
        "trust_report": render_trust_boundaries(state),
        "test_report": render_test_architecture(state),
        "findings_report": render_prioritized_findings(findings),
        "migration_report": render_migration_plan(findings),
    }
    for kind, value in markdown_values.items():
        paths[kind].write_text(value, encoding="utf-8")
    for index, prompt in enumerate(prompts, start=1):
        paths[f"codex_prompt_{index}"].write_text(prompt["body"] + "\n", encoding="utf-8")

    run_dir = Path(ctx["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    source_trace = run_dir / "llm_trace.jsonl"
    if not source_trace.is_file():
        raise ValueError("Required metadata-only LLM trace is missing after final audit.")
    paths["llm_trace"].write_text(source_trace.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "final_artifact.json").write_text(_json(assessment), encoding="utf-8")
    result = {
        "identity": {"blueprint_id": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run_id": ctx["run_id"]},
        "run": {"run_id": ctx["run_id"], "status": "completed"},
        "final_artifact": assessment,
        "output_files": output_files,
        "llm": llm_analysis.get("aggregate_usage") or state.get("llm_usage") or {},
    }
    (run_dir / "result.json").write_text(_json(result), encoding="utf-8")
    state["final_artifact"] = assessment
    write_state(ctx, state)
    return {"final_artifact": assessment, "output_files": output_files}


def render_report(assessment: dict[str, Any]) -> str:
    """Compatibility wrapper for consumers importing the v1 renderer."""
    return render_architecture_report(assessment)


def _safe_source(source: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in source.items() if key != "root"}


def _summary(metrics: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    high = sum(1 for item in findings if item.get("severity") in {"high", "critical"})
    medium = sum(1 for item in findings if item.get("severity") == "medium")
    return (
        f"Static evidence covered {metrics.get('module_count', 0)} modules, "
        f"{metrics.get('symbol_count', 0)} symbols, and {metrics.get('dependency_edge_count', 0)} internal dependencies. "
        f"It produced {high} high-priority and {medium} medium-priority hypotheses after evidence triangulation; "
        "every recommendation remains subject to counter-evidence and current-checkout verification."
    )


def _confidence(findings: list[dict[str, Any]]) -> str:
    if findings and all(item.get("confidence") == "high" for item in findings):
        return "high"
    if any(item.get("confidence") in {"high", "medium"} for item in findings):
        return "medium"
    return "low"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "architecture-improvement"


def _render_prompt_index(prompts: list[dict[str, Any]]) -> str:
    lines = [
        "# Copy-ready architecture prompts",
        "",
        "Choose one numbered Markdown file and paste it into Codex or another coding agent. Each file is a complete implementation prompt; validate its evidence against the current checkout first.",
        "",
    ]
    if not prompts:
        lines.append("No prioritized implementation prompts were produced.")
        return "\n".join(lines) + "\n"

    for index, prompt in enumerate(prompts, start=1):
        slug = _slug(prompt.get("title") or prompt.get("prompt_id") or str(index))
        filename = f"{index:02d}-{slug}.md"
        priority = prompt.get("priority") or "unranked"
        lines.append(f"- [{prompt.get('title') or filename}]({filename}) — priority: {priority}")
    return "\n".join(lines) + "\n"


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"
