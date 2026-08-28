"""Research packet verification, composition, and durable customer outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .autonomous import _experiment_concepts
from .common import BLOCKED_ACTIONS, BLUEPRINT_ID, BLUEPRINT_NAME, OUTPUT_TYPE, RESEARCH_ACTIONS
from .evidence import _status_counts, resolve_output_folder
from .state import _inputs, _save, _state


def _safe_warning(item: Any) -> dict[str, Any]:
    warning = dict(item) if isinstance(item, dict) else {"message": str(item)}
    if warning.get("path"):
        warning["staged_name"] = Path(str(warning["path"])).name
        warning.pop("path", None)
    return warning


def _markdown_value(value: Any) -> str:
    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {_markdown_value(item)}" for key, item in value.items()
        )
    if isinstance(value, list):
        return ", ".join(_markdown_value(item) for item in value)
    return str(value)


def _rag_summary(rag: dict[str, Any]) -> dict[str, Any]:
    config = rag.get("config") if isinstance(rag.get("config"), dict) else {}
    index = rag.get("index_summary") if isinstance(rag.get("index_summary"), dict) else {}
    return {
        "enabled": bool(rag.get("enabled")),
        "status": rag.get("status"),
        "retrieval_backend": rag.get("retrieval_backend") or rag.get("backend"),
        "embedding_provider": config.get("embedding_provider"),
        "embedding_model": config.get("embedding_model"),
        "indexed_count": index.get("indexed_count"),
        "skipped_count": index.get("skipped_count"),
        "fallback_active": bool(rag.get("fallback_active")),
        "citations": list(rag.get("citations") or []),
        "user_documents_indexed": list(rag.get("user_documents_indexed") or []),
        "knowledge_files": [
            {key: item.get(key) for key in ("name", "sha256", "chars") if item.get(key) is not None}
            for item in rag.get("knowledge_files") or []
            if isinstance(item, dict)
        ],
        "warnings": [_safe_warning(item) for item in rag.get("warnings") or []],
    }


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
    llm_usage: dict[str, Any] | None = None,
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
    local_count = int(evidence.get("usable_local_document_count") or 0)
    public_count = int(evidence.get("usable_public_source_count") or 0)
    llm_usage = llm_usage or {}
    executive_synthesis = (
        recommendation.get("executive_synthesis")
        if isinstance(recommendation.get("executive_synthesis"), dict)
        else {}
    )
    calls = int(llm_usage.get("calls") or 0)
    fallback_calls = int(llm_usage.get("fallback_calls") or 0)
    if calls and fallback_calls >= calls:
        generation_mode = "deterministic_fallback"
    elif fallback_calls:
        generation_mode = "mixed_model_and_fallback"
    elif calls:
        generation_mode = "model_generated"
    else:
        generation_mode = "deterministic_only"
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
        "schema_version": "mn.blueprint.research_assistant.v2",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": status,
        "research_goal": inputs.get("research_goal"),
        "research_domain": inputs.get("research_domain"),
        "research_question": inputs.get("research_question"),
        "scope": inputs.get("scope"),
        "executive_summary": str(
            executive_synthesis.get("executive_summary")
            or (
                f"Prepared {len(hypotheses)} review-only candidate hypotheses from "
                f"{local_count} usable local documents and {public_count} observed public sources. "
                "The packet is suitable for planning and qualified review, not as validation of any hypothesis. "
                f"Recommended posture: {recommended_action} ({confidence} confidence)."
            )
        ),
        "key_findings": list(executive_synthesis.get("key_findings") or []),
        "decision_implications": list(
            executive_synthesis.get("decision_implications") or []
        ),
        "synthesis_caveats": list(executive_synthesis.get("caveats") or []),
        "recommended_action": recommended_action,
        "confidence": confidence,
        "recommendation_rationale": recommendation_rationale,
        "evidence": {
            "deterministic": evidence,
            "documents": [
                {
                    **{key: value for key, value in item.items() if key not in {"text", "path"}},
                    "staged_name": item.get("name"),
                }
                for item in documents
            ],
            "public_sources": sources,
        },
        "hypothesis_ledger": hypotheses,
        "question_decomposition": autonomous.get("question_decomposition") or {},
        "source_analysis": autonomous.get("source_analysis") or {},
        "critique_ledger": autonomous.get("critique_ledger") or [],
        "hypothesis_ranking": autonomous.get("ranking") or [],
        "evidence_map": [
            {
                "hypothesis_id": item.get("hypothesis_id"),
                "evidence_status": item.get("evidence_status"),
                "links": item.get("evidence_links") or [],
            }
            for item in hypotheses
        ],
        "adversarial_review": {
            "required_for_each_hypothesis": ["counterargument", "disconfirming_observation"],
            "actor_findings": actor_findings,
        },
        "autonomous_research": autonomous,
        "experiment_concepts": _experiment_concepts(hypotheses, inputs),
        "research_procedure": [
            {"stage": "frame", "result": "Goal, question, scope, success criteria, and constraints normalized."},
            {"stage": "evidence", "result": "Approved local sources extracted, indexed, and assigned stable source refs; public retrieval retained with access status."},
            {"stage": "source_analysis", "result": "The model reads bounded source excerpts, extracts stated observations, and records limitations, agreements, tensions, and gaps."},
            {"stage": "question_decomposition", "result": "The model separates the decision into answerable subquestions, definitions, assumptions, evidence needs, and stop conditions."},
            {"stage": "competing_hypotheses", "result": "The model generates genuinely competing mechanisms with measurable predictions and source references."},
            {"stage": "adversarial_review", "result": "Each hypothesis receives a separate critique covering alternatives, confounders, measurement risks, boundary conditions, and disconfirmation."},
            {"stage": "probe_planning", "result": "The model requests only bounded tools or code probes tied to a named gap; the isolated Docker worker records every observation."},
            {"stage": "revision", "result": "The model revises, merges, or rejects candidates after reviewing critiques and probe observations."},
            {"stage": "experiment_design", "result": "The model designs a complete review-only test contract for every surviving hypothesis."},
            {"stage": "meta_review", "result": "An independent pass ranks candidates by traceability, falsifiability, decision value, and misleading-claim risk."},
            {"stage": "executive_synthesis", "result": "A final model pass integrates source findings, critiques, tests, ranking, implications, and caveats without introducing new facts."},
            {"stage": "audit", "result": "Traceability, falsifiability, counterarguments, source validity, and experiment completeness checked before publication."},
            {"stage": "human_review", "result": "All experiments and consequential actions remain blocked pending qualified approval."},
        ],
        "generation_provenance": {
            "mode": generation_mode,
            "llm_calls": calls,
            "fallback_calls": fallback_calls,
            "provider": llm_usage.get("provider"),
            "model": llm_usage.get("model"),
            "research_phase_count": len(autonomous.get("research_phase_trace") or []),
            "live_model_required": bool(autonomous.get("live_model_required")),
            "note": "Fallback content is template- and input-derived and must not be represented as successful model synthesis." if fallback_calls else "No model fallback was recorded.",
        },
        "knowledge_rag": _rag_summary(rag),
        "evidence_gaps": list(
            dict.fromkeys(
                [
                    *[str(item) for item in evidence.get("evidence_gaps") or []],
                    *[str(item) for item in autonomous.get("unresolved_gaps") or []],
                ]
            )
        ),
        "warnings": [_safe_warning(item) for item in warnings],
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
    hypotheses = packet.get("hypothesis_ledger") or []
    experiments = packet.get("experiment_concepts") or []
    valid_refs = set(packet.get("source_refs") or [])
    autonomous = packet.get("autonomous_research") or {}
    phase_names = {
        str(item.get("phase") or "")
        for item in autonomous.get("research_phase_trace") or []
        if isinstance(item, dict)
    }
    required_phases = {
        "source_analysis",
        "question_decomposition",
        "competing_hypothesis_generation",
        "gap_and_probe_planning",
        "evidence_and_probe_revision",
        "experiment_design",
        "meta_review_and_ranking",
        "executive_synthesis",
    }
    provenance = packet.get("generation_provenance") or {}
    legacy_placeholders = ("pre-specified measurement", "primary outcome", "relevant confounders")
    checks = [
        {"name": "research_action_valid", "passed": packet.get("recommended_action") in RESEARCH_ACTIONS},
        {"name": "usable_evidence_present", "passed": usable_evidence},
        {"name": "packet_status_matches_evidence", "passed": packet.get("status") == expected_status},
        {"name": "hypotheses_labeled", "passed": all(item.get("status") == "hypothesis_for_review" for item in hypotheses)},
        {"name": "hypothesis_predictions_are_specific", "passed": bool(hypotheses) and all(item.get("prediction") and not any(marker in str(item.get("prediction")).lower() for marker in legacy_placeholders) for item in hypotheses)},
        {"name": "hypothesis_source_refs_are_valid", "passed": bool(hypotheses) and all(item.get("evidence_support") and set(item.get("evidence_support") or []) <= valid_refs for item in hypotheses)},
        {"name": "experiment_procedures_are_complete", "passed": len(experiments) == len(hypotheses) and all(item.get("unit_of_analysis") and item.get("primary_outcome") and len(item.get("procedure") or []) >= 4 and item.get("decision_rule") and item.get("stop_conditions") for item in experiments)},
        {"name": "review_boundary_present", "passed": bool(packet.get("review_boundary"))},
        {"name": "autonomous_isolation_declared", "passed": autonomous.get("isolation_required") is True and autonomous.get("runner") == "docker_worker"},
        {"name": "autonomous_trace_present", "passed": bool((autonomous.get("session") or {}).get("trace"))},
        {"name": "deep_research_phases_complete", "passed": required_phases <= phase_names and any(name.startswith("adversarial_review_") for name in phase_names)},
        {"name": "source_analysis_present", "passed": bool((packet.get("source_analysis") or {}).get("source_assessments"))},
        {"name": "live_model_backed_when_required", "passed": not provenance.get("live_model_required") or (provenance.get("mode") == "model_generated" and int(provenance.get("fallback_calls") or 0) == 0 and int(provenance.get("research_phase_count") or 0) >= 9)},
        {"name": "generation_mode_disclosed", "passed": bool((packet.get("generation_provenance") or {}).get("mode"))},
        {"name": "internal_document_paths_redacted", "passed": all("path" not in item for item in ((packet.get("evidence") or {}).get("documents") or []))},
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
    provenance = packet.get("generation_provenance") or {}
    lines = [
        "# Research Assistant Brief",
        "",
        f"**Research goal:** {packet.get('research_goal') or 'Not specified'}",
        f"**Domain:** {packet.get('research_domain') or 'General'}",
        f"**Research question:** {packet.get('research_question') or 'Not specified'}",
        f"**Scope:** {packet.get('scope') or 'Not specified'}",
        f"**Status:** {packet.get('status')}",
        f"**Review posture:** {packet.get('recommended_action')}",
        f"**Confidence:** {packet.get('confidence')}",
        "",
        "## Executive Summary",
        str(packet.get("executive_summary") or ""),
        f"\n**Research rationale:** {packet.get('recommendation_rationale') or 'Not provided'}",
        "",
        "### Key Findings",
    ]
    lines.extend(f"- {item}" for item in packet.get("key_findings") or ["No key findings recorded."])
    lines.extend(["", "### Decision Implications"])
    lines.extend(
        f"- {item}"
        for item in packet.get("decision_implications")
        or ["Resolve the evidence gaps before taking consequential action."]
    )
    if packet.get("synthesis_caveats"):
        lines.extend(["", "### Caveats"])
        lines.extend(f"- {item}" for item in packet.get("synthesis_caveats") or [])
    lines.extend([
        "",
        "## Generation Notes",
        f"- Generation mode: `{provenance.get('mode') or 'unknown'}`",
        f"- Provider/model: `{provenance.get('provider') or 'unknown'}` / `{provenance.get('model') or 'unknown'}`",
        f"- Model calls: {provenance.get('llm_calls', 0)}; research phases: {provenance.get('research_phase_count', 0)}; fallback calls: {provenance.get('fallback_calls', 0)}",
        f"- {provenance.get('note') or 'No generation note recorded.'}",
        "",
        "## Evidence Reviewed",
        f"- Local documents reviewed: {deterministic.get('document_count', 0)}",
        f"- Public sources observed: {deterministic.get('public_source_count', 0)}",
        f"- Usable evidence present: {'Yes' if deterministic.get('usable_evidence_present') else 'No'}",
        "- Evidence links below identify relevant context; they do not validate a candidate hypothesis.",
    ])
    for document in (packet.get("evidence") or {}).get("documents") or []:
        lines.append(
            f"- `{document.get('source_ref')}` — {document.get('name')} ({document.get('status')}; {document.get('extraction_method')})"
        )
    for source in (packet.get("evidence") or {}).get("public_sources") or []:
        lines.append(
            f"- `{source.get('source_ref')}` — {source.get('title') or source.get('url')} ({source.get('status')})"
        )
    csv_profiles = [
        item
        for item in deterministic.get("document_profiles") or []
        if item.get("suffix") == ".csv" and item.get("profile_status") == "described_not_interpreted"
    ]
    if csv_profiles:
        lines.extend(["", "## Dataset Profiles"])
    for profile in csv_profiles:
        lines.append(
            f"### `{profile.get('source_ref')}` — {profile.get('row_count', 0)} rows, {len(profile.get('columns') or [])} columns"
        )
        lines.append("Descriptive input statistics only; no causal or validation claim is implied.")
        numeric_summary = profile.get("numeric_summary") or {}
        if numeric_summary:
            lines.append("- Numeric summaries:")
            for name, values in list(numeric_summary.items())[:10]:
                lines.append(
                    f"  - `{name}`: min {values.get('min')}, mean {values.get('mean')}, max {values.get('max')} (n={values.get('count')})"
                )
        categorical_summary = profile.get("categorical_summary") or {}
        useful_categories = [
            (name, values)
            for name, values in categorical_summary.items()
            if 1 < len(values) < int(profile.get("row_count") or 0)
            and name.lower() != "id"
            and not name.lower().endswith("_id")
        ]
        if useful_categories:
            lines.append("- Category counts:")
            for name, values in useful_categories[:5]:
                rendered = ", ".join(f"{item.get('value')}={item.get('count')}" for item in values)
                lines.append(f"  - `{name}`: {rendered}")
    question_decomposition = packet.get("question_decomposition") or {}
    lines.extend(["", "## Research Decomposition"])
    for item in question_decomposition.get("subquestions") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- **{item.get('subquestion_id') or 'Question'}:** {item.get('question')}"
        )
        if item.get("decision_relevance"):
            lines.append(f"  - Decision relevance: {item.get('decision_relevance')}")
        if item.get("evidence_needed"):
            needed = item.get("evidence_needed")
            rendered = ", ".join(str(value) for value in needed) if isinstance(needed, list) else str(needed)
            lines.append(f"  - Evidence needed: {rendered}")
    if question_decomposition.get("key_definitions"):
        lines.append("- Key definitions:")
        lines.extend(
            f"  - {_markdown_value(item)}"
            for item in question_decomposition.get("key_definitions") or []
        )
    if question_decomposition.get("assumptions_to_test"):
        lines.append("- Assumptions to test:")
        lines.extend(
            f"  - {_markdown_value(item)}"
            for item in question_decomposition.get("assumptions_to_test") or []
        )
    source_analysis = packet.get("source_analysis") or {}
    lines.extend(["", "## Source Analysis"])
    for item in source_analysis.get("source_assessments") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"### `{item.get('source_ref') or 'unknown source'}` ({item.get('source_type') or 'unknown'})"
        )
        lines.append(
            f"- Synthesis use: {item.get('use_in_synthesis') or 'Not specified'}"
        )
        lines.append("- Relevant observations:")
        lines.extend(
            f"  - {_markdown_value(observation)}"
            for observation in item.get("relevant_observations") or ["None recorded."]
        )
        lines.append("- Limitations:")
        lines.extend(
            f"  - {_markdown_value(limitation)}"
            for limitation in item.get("limitations") or ["None recorded."]
        )
    if source_analysis.get("cross_source_agreements"):
        lines.append("- Cross-source agreements:")
        lines.extend(
            f"  - {item}" for item in source_analysis.get("cross_source_agreements") or []
        )
    if source_analysis.get("cross_source_tensions"):
        lines.append("- Cross-source tensions:")
        lines.extend(
            f"  - {item}" for item in source_analysis.get("cross_source_tensions") or []
        )
    lines.extend(["", "## Research Procedure"])
    for index, item in enumerate(packet.get("research_procedure") or [], start=1):
        lines.append(f"{index}. **{item.get('stage')}** — {item.get('result')}")
    lines.extend([
        "",
        "## Candidate Hypotheses",
    ])
    experiments = {item.get("hypothesis_id"): item for item in packet.get("experiment_concepts") or []}
    critiques = {
        item.get("hypothesis_id"): item
        for item in packet.get("critique_ledger") or []
        if isinstance(item, dict) and item.get("hypothesis_id")
    }
    for hypothesis in packet.get("hypothesis_ledger") or []:
        experiment = experiments.get(hypothesis.get("hypothesis_id")) or {}
        critique = critiques.get(hypothesis.get("hypothesis_id")) or {}
        lines.extend([
            f"### {hypothesis.get('hypothesis_id')}: {hypothesis.get('statement')}",
            f"- Evidence status: {hypothesis.get('evidence_status')}",
            f"- Rank / priority score: {hypothesis.get('rank') or 'Not ranked'} / {hypothesis.get('priority_score') if hypothesis.get('priority_score') is not None else 'Not scored'}",
            f"- Ranking rationale: {hypothesis.get('ranking_rationale') or 'Pending qualified review.'}",
            f"- Prediction: {hypothesis.get('prediction')}",
            f"- Relevant source refs: {', '.join(f'`{ref}`' for ref in hypothesis.get('evidence_support') or []) or 'None'}",
            f"- Counterargument: {hypothesis.get('counterargument')}",
            f"- Disconfirming observation: {hypothesis.get('disconfirming_observation')}",
        ])
        if hypothesis.get("assumptions"):
            lines.append("- Assumptions:")
            lines.extend(f"  - {item}" for item in hypothesis["assumptions"])
        if critique:
            lines.extend(["", "#### Independent Adversarial Review"])
            if critique.get("strongest_counterargument"):
                lines.append(
                    f"- Strongest counterargument: {_markdown_value(critique.get('strongest_counterargument'))}"
                )
            for label, key in (
                ("Alternative explanations", "alternative_explanations"),
                ("Confounders", "confounders"),
                ("Measurement risks", "measurement_risks"),
                ("Boundary conditions", "boundary_conditions"),
                ("Decisive disconfirmation", "decisive_disconfirming_observations"),
            ):
                if critique.get(key):
                    lines.append(f"- {label}:")
                    lines.extend(
                        f"  - {_markdown_value(value)}"
                        for value in critique.get(key) or []
                    )
            if critique.get("revision_recommendation"):
                lines.append(
                    f"- Revision recommendation: {_markdown_value(critique.get('revision_recommendation'))}"
                )
        lines.extend([
            "",
            "#### Test Procedure",
            f"- Objective: {experiment.get('objective')}",
            f"- Unit of analysis: {experiment.get('unit_of_analysis')}",
            f"- Baseline: {experiment.get('baseline')}",
            f"- Intervention: {experiment.get('intervention')}",
            f"- Primary outcome: {experiment.get('primary_outcome')}",
            f"- Decision rule: {experiment.get('decision_rule')}",
            f"- Analysis plan: {experiment.get('analysis_plan')}",
            f"- Measurements: {', '.join(str(item) for item in experiment.get('measurements') or []) or 'Not specified'}",
            "- Procedure:",
        ])
        lines.extend(f"  {index}. {step}" for index, step in enumerate(experiment.get("procedure") or [], start=1))
        lines.append("- Stop conditions:")
        lines.extend(f"  - {item}" for item in experiment.get("stop_conditions") or [])
        lines.append("")
    actor_findings = (packet.get("adversarial_review") or {}).get("actor_findings") or {}
    if actor_findings:
        lines.extend(["", "## Specialist Reviews"])
        for actor_id, finding in actor_findings.items():
            if not isinstance(finding, dict):
                continue
            lines.append(f"### {finding.get('role') or actor_id}")
            lines.append(str(finding.get("summary") or "No summary recorded."))
            for label, key in (("Findings", "findings"), ("Risks", "risks")):
                if finding.get(key):
                    lines.append(f"- {label}:")
                    lines.extend(
                        f"  - {_markdown_value(value)}"
                        for value in finding.get(key) or []
                    )
            if finding.get("recommended_next_step"):
                lines.append(
                    f"- Recommended next step: {_markdown_value(finding.get('recommended_next_step'))}"
                )
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
    packet["output_files"] = [
        {"kind": kind, "path": path.name} for kind, path in paths.items()
    ]
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
    if (
        autonomous.get("isolation_required") is not True
        or autonomous.get("runner") != "docker_worker"
        or not session.get("trace")
    ):
        raise ValueError("autonomous output lacks the required Docker-worker isolation and trace contract")
    audit = state.get("packet_audit") or {}
    if audit.get("status") == "needs_revision" and "evidence_references_present" not in set(audit.get("blocking_findings") or []):
        raise ValueError("research packet failed deterministic traceability and falsifiability checks")
    final = build_research_packet(
        inputs,
        state.get("evidence") or {},
        state.get("recommendation") or {},
        state.get("rag") or {},
        state.get("sources") or [],
        state.get("warnings") or [],
        state.get("documents") or [],
        state.get("actor_findings") or {},
        autonomous,
        ctx["run_id"],
        state.get("llm_usage") or {},
    )
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
