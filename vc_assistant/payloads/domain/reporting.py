"""VC report rendering, coverage, artifact quality, and health policy."""

from __future__ import annotations

from .common import *
from .analysis import research_gap_followups
from .evidence import is_substantive_public_source
from .intake import slugify
from .knowledge import knowledge_rag_is_required, public_knowledge_rag_state

def render_markdown(analysis: dict[str, Any], sources: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    claims = list(analysis.get("claim_records") or [])
    evidence_items = {str(item.get("evidence_id")): item for item in (analysis.get("evidence_items") or [])}
    positive_claims = sorted(
        [claim for claim in claims if float(claim.get("motion_strength") or 0) > 0],
        key=lambda item: (float(item.get("weighted_motion") or 0), int(item.get("importance") or 0)),
        reverse=True,
    )[:5]
    negative_claims = sorted(
        [claim for claim in claims if float(claim.get("motion_strength") or 0) < 0],
        key=lambda item: (abs(float(item.get("weighted_motion") or 0)), int(item.get("importance") or 0)),
        reverse=True,
    )[:5]
    evidence_rows = sorted(
        claims,
        key=lambda item: (int(item.get("importance") or 0), int(item.get("net_confidence") or 0)),
        reverse=True,
    )[:8]
    cap_reasons = [str(item.get("reason") or "") for item in (analysis.get("score_caps") or []) if item.get("reason")]
    missing_evidence = dedupe_list(
        [
            missing
            for claim in claims
            for missing in (claim.get("required_next_evidence") or [])[:3]
            if int(claim.get("net_confidence") or 0) < 70
        ],
        10,
    )
    lines = [
        f"# {analysis['company_name']} VC Heuristic Report",
        "",
        "This is a score-only early screening report with evidence-grounded claims. It separates investment attractiveness, evidence confidence, and diligence priority; it does not issue an investment decision.",
        "",
        f"Verdict: {str(analysis.get('recommendation') or 'needs_review').replace('_', ' ')}",
        f"Investment score: {analysis.get('investment_score') if analysis.get('investment_score') is not None else 'insufficient evidence'} / 100",
        f"Evidence quality: {analysis.get('evidence_quality_score', 0)} / 100",
        f"Confidence: {str(analysis.get('confidence_band') or 'not_reliable').replace('_', ' ')}",
        f"Fund profile: {analysis.get('fund_profile', 'generalist')}",
        "",
        "## Why This Is Interesting",
    ]
    if positive_claims:
        for claim in positive_claims:
            lines.append(f"- {claim.get('canonical_claim')} (confidence {claim.get('net_confidence')}%, importance {claim.get('importance')})")
    else:
        lines.append("- No positive investor-relevant claim was supported strongly enough to summarize.")
    lines += ["", "## Main Concerns"]
    if negative_claims:
        for claim in negative_claims:
            lines.append(f"- {claim.get('canonical_claim')} (confidence {claim.get('net_confidence')}%, importance {claim.get('importance')})")
    else:
        lines.append("- No explicit negative claim was found; this does not remove the need for diligence.")
    if cap_reasons:
        lines += ["", "## Score Caps"]
        for reason in cap_reasons:
            lines.append(f"- {reason}")
    lines += ["", "## Dimension Scores"]
    for dimension, score in (analysis.get("dimension_scores") or {}).items():
        lines.append(f"- {dimension}: {score}")
    lines += [
        "",
        "## Most Important Claims",
        "| Claim | Direction | Confidence | Importance | Evidence |",
        "|---|---:|---:|---:|---|",
    ]
    if evidence_rows:
        for claim in evidence_rows:
            refs = []
            for evidence_id in claim.get("evidence_ids") or []:
                item = evidence_items.get(str(evidence_id)) or {}
                refs.append(str(item.get("filename") or item.get("source_url") or evidence_id))
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(claim.get("canonical_claim")),
                        markdown_cell(claim.get("motion_direction")),
                        markdown_cell(claim.get("net_confidence")),
                        markdown_cell(claim.get("importance")),
                        markdown_cell(", ".join(dedupe_list(refs, 3))),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| No normalized claims found | neutral | 0 | 0 | none |")
    truth_discovery = analysis.get("truth_discovery") or {}
    truth_rows = list(truth_discovery.get("claim_truth_scores") or [])[:8]
    reliability_rows = sorted(
        list(truth_discovery.get("source_reliability") or []),
        key=lambda item: float(item.get("combined_reliability") or item.get("prior_reliability") or 0),
        reverse=True,
    )[:8]
    lines += ["", "## Truth Discovery"]
    for note in truth_discovery.get("notes") or ["Truth discovery was not available for this run."]:
        lines.append(f"- {note}")
    if truth_rows:
        lines += [
            "",
            "| Claim | Log-Odds Probability | Crowd-Kit Probability | Final Truth Probability | Notes |",
            "|---|---:|---:|---:|---|",
        ]
        for row in truth_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(row.get("claim")),
                        markdown_cell(row.get("log_odds_probability")),
                        markdown_cell(row.get("crowdkit_probability") if row.get("crowdkit_probability") is not None else "n/a"),
                        markdown_cell(row.get("final_truth_probability")),
                        markdown_cell(row.get("note")),
                    ]
                )
                + " |"
            )
    if reliability_rows:
        lines += [
            "",
            "| Source | Source Type | Prior Reliability | Truth-Discovery Reliability | Combined Reliability |",
            "|---|---|---:|---:|---:|",
        ]
        for row in reliability_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(row.get("source_id")),
                        markdown_cell(row.get("source_type")),
                        markdown_cell(round(float(row.get("prior_reliability") or 0), 3)),
                        markdown_cell(round(float(row.get("truth_discovery_reliability")), 3) if row.get("truth_discovery_reliability") is not None else "n/a"),
                        markdown_cell(round(float(row.get("combined_reliability") or 0), 3)),
                    ]
                )
                + " |"
            )
    bayesian_explanations = list(analysis.get("bayesian_claim_explanations") or [])
    if bayesian_explanations:
        lines += ["", "## Bayesian Claim Explanation"]
        for explanation in bayesian_explanations:
            if explanation.get("status") == "failed":
                lines.append(f"- {markdown_cell(explanation.get('message') or explanation.get('warning'))}")
                continue
            markdown = str(explanation.get("markdown") or "").strip()
            if markdown:
                lines.append(markdown)
            else:
                lines += [
                    f"### {markdown_cell(explanation.get('canonical_claim') or explanation.get('claim_type'))}",
                    f"- Prior probability: {round(float(explanation.get('prior_probability') or 0) * 100)}%",
                    f"- Posterior probability: {round(float(explanation.get('posterior_probability') or 0) * 100)}%",
                    f"- Main confidence limiter: {markdown_cell(explanation.get('main_confidence_limiter') or 'none')}",
                    f"- Investor interpretation: {markdown_cell(explanation.get('investor_interpretation') or 'Structured belief update only.')}",
                ]
    lines += ["", "## Required Diligence"]
    if missing_evidence:
        for idx, item in enumerate(missing_evidence, start=1):
            lines.append(f"{idx}. {item}")
    else:
        lines.append("1. Review primary evidence and customer references before making any investment decision.")
    lines += [
        "",
        "## Method Score Appendix",
        f"- Method average score: {analysis.get('method_average_score') if analysis.get('method_average_score') is not None else 'insufficient_evidence'}",
        "",
    ]
    for method_id in METHOD_IDS:
        method = analysis["methods"][method_id]
        evidence_summary = method.get("evidence_summary") or {}
        assumptions = method.get("assumptions") or []
        lines += [
            f"### {method_id.replace('_', ' ').title()}",
            f"- Status: {method['status']}",
            f"- Score: {method.get('score') if method.get('score') is not None else 'insufficient_evidence'}",
            f"- Memory hook: {method['memory_hook']}",
            f"- Why: {evidence_summary.get('status_reason', 'not recorded')}",
            f"- Evidence refs: {len(method.get('evidence_refs') or [])}",
            f"- Assumptions: {'; '.join(assumptions) if assumptions else 'none'}",
            f"- Missing evidence: {', '.join(method.get('missing_evidence') or []) if method.get('missing_evidence') else 'none'}",
        ]
    composite_evidence = (analysis.get("result_evidence") or {}).get("composite_score") or {}
    lines += [
        "",
        "## Result Evidence",
        f"- Investment score basis: {composite_evidence.get('why', 'not recorded')}",
        f"- Scored methods: {analysis.get('evidence_summary', {}).get('composite_score_evidence', {}).get('scored_method_count', 0)}",
        f"- Missing method evidence: {', '.join(analysis.get('evidence_summary', {}).get('missing_methods', [])) or 'none'}",
        "",
        "## Evidence",
        f"- Local documents: {len(evidence)}",
        f"- Public sources: {len(sources)}",
        f"- Normalized evidence items: {len(analysis.get('evidence_items') or [])}",
        f"- Normalized claims: {len(claims)}",
        "",
    ]
    for item in evidence[:8]:
        lines.append(f"- {item['filename']}: {item.get('extraction_method')} ({item.get('sha256', '')[:12]})")
    lines += ["", "## Public Sources"]
    for source in sources:
        lines.append(f"- {source['title']}: {source['url']} ({source.get('source_quality_label', 'thin_signal')})")
    lines += ["", "## Research Gaps And Follow-Ups"]
    for item in research_gap_followups(analysis, sources):
        lines.append(f"- {item}")
    lines += ["", "## User Decision Boundary", "Use the claims, confidence scores, assumptions, and source refs to decide what to review next."]
    return "\n".join(lines) + "\n"

def build_research_coverage(research_ledgers: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    coverage = shared_build_research_coverage(research_ledgers)
    for company in coverage.get("companies", []):
        name = str(company.get("company_name") or "")
        ledger = research_ledgers.get(name) if isinstance(research_ledgers.get(name), dict) else {}
        company["company_slug"] = slugify(name)
        company["agent_counts"] = {agent_id: len(sources) for agent_id, sources in ledger.items()}
        company["statuses"] = sorted({str(source.get("status") or "") for sources in ledger.values() for source in sources if source.get("status")})
    coverage["generated_at"] = utc_now_iso()
    return coverage

def build_method_coverage(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    shared = shared_build_method_coverage(analyses)
    shared_companies = {
        str(company.get("company_name") or ""): company
        for company in shared.get("companies") or []
    }
    companies = [
        {
            "company_name": analysis["company_name"],
            "company_slug": analysis["company_slug"],
            "method_statuses": shared_companies.get(analysis["company_name"], {}).get("method_statuses", {}),
            "missing_methods": shared_companies.get(analysis["company_name"], {}).get("missing_methods", []),
        }
        for analysis in analyses
    ]
    return {"generated_at": utc_now_iso(), "method_ids": METHOD_IDS, "companies": companies}

def quality_check(status: str, message: str, **metadata: Any) -> dict[str, Any]:
    return shared_quality_check(status=status, message=message, **metadata)

def build_artifact_quality_report(
    *,
    analyses: list[dict[str, Any]],
    company_records: dict[str, list[dict[str, Any]]],
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
    output_files: list[dict[str, Any]],
    knowledge_rag: dict[str, Any] | None,
    actor_findings: dict[str, Any],
    actor_review_settings: dict[str, Any],
) -> dict[str, Any]:
    """Summarize whether every generated report has auditable evidence and source attempts."""
    files_by_company: dict[str, set[str]] = {}
    for item in output_files:
        company = str(item.get("company") or "")
        path = Path(str(item.get("path") or ""))
        if company and path.name:
            files_by_company.setdefault(company, set()).add(path.name)
    required_files = {"analysis.json", "analysis.md", "method_scores.json", "research_plan.json", "research_sources.json", "evidence.json", "warnings.json"}
    selected_actor_ids = set(actor_review_settings.get("llm_actor_ids") or [])
    actor_reviewed = {
        actor_id
        for actor_id in selected_actor_ids
        if isinstance(actor_findings.get(actor_id), dict) and actor_findings[actor_id].get("status") != "not_llm_reviewed"
    }
    rag_required = knowledge_rag_is_required(knowledge_rag or {})
    rag_ready = public_knowledge_rag_state(knowledge_rag or {}).get("status") in {"ready", "disabled"}
    companies: list[dict[str, Any]] = []
    for analysis in analyses:
        company = analysis["company_name"]
        records = company_records.get(company, [])
        ledger = research_ledgers.get(company, {})
        sources = flattened_sources(ledger)
        substantive_sources = [source for source in sources if is_substantive_public_source(source)]
        public_tool_attempts = [
            source
            for source in sources
            if str(source.get("skill") or "").startswith(
                ("web_browser_skill", "financial_public_data_tool")
            )
            or str(source.get("url") or "").startswith("financial_tool://")
        ]
        failed_tool_attempts = [source for source in public_tool_attempts if source.get("status") in WARNING_SOURCE_STATUSES]
        financial_sources = [
            source
            for source in sources
            if source.get("skill") == "financial_public_data_tool" or str(source.get("url") or "").startswith("financial_tool://")
        ]
        missing_files = sorted(required_files - files_by_company.get(company, set()))
        method_missing_count = len(analysis.get("evidence_summary", {}).get("missing_methods") or [])
        checks = {
            "local_evidence": quality_check(
                "passed" if records else "warning",
                "Local startup packet evidence was captured." if records else "No local startup packet evidence was available for this company.",
                record_count=len(records),
            ),
            "public_research": quality_check(
                "passed" if substantive_sources else ("warning" if public_tool_attempts else "warning"),
                "Substantive public research sources were captured." if substantive_sources else "Public research has only failed, configured, planned, or thin-source records.",
                source_count=len(sources),
                substantive_source_count=len(substantive_sources),
                public_tool_attempt_count=len(public_tool_attempts),
                failed_tool_attempt_count=len(failed_tool_attempts),
            ),
            "financial_tool": quality_check(
                "passed" if financial_sources else "warning",
                "Deterministic financial comparable tool output is present." if financial_sources else "Deterministic financial comparable tool output is missing.",
                source_count=len(financial_sources),
            ),
            "method_evidence": quality_check(
                "passed" if method_missing_count == 0 else "warning",
                "All VC methods had enough evidence to score." if method_missing_count == 0 else "One or more VC methods are marked insufficient evidence.",
                missing_method_count=method_missing_count,
                missing_methods=analysis.get("evidence_summary", {}).get("missing_methods") or [],
            ),
            "rag_knowledge": quality_check(
                "passed" if rag_ready else ("failed" if rag_required else "warning"),
                "Required RAG knowledge was ready or disabled by config." if rag_ready else "RAG knowledge was not ready.",
                required=rag_required,
                rag_status=public_knowledge_rag_state(knowledge_rag or {}).get("status"),
            ),
            "actor_review": quality_check(
                "passed" if selected_actor_ids <= actor_reviewed else "warning",
                "Selected LLM actor reviewers produced findings." if selected_actor_ids <= actor_reviewed else "Some selected LLM actor reviewers did not produce live findings.",
                selected_actor_ids=sorted(selected_actor_ids),
                reviewed_actor_ids=sorted(actor_reviewed),
            ),
            "output_files": quality_check(
                "passed" if not missing_files else "failed",
                "Required per-company report files were written." if not missing_files else "Required per-company report files are missing.",
                missing_files=missing_files,
            ),
        }
        status_values = [item["status"] for item in checks.values()]
        company_status = "failed" if "failed" in status_values else ("warning" if "warning" in status_values else "passed")
        companies.append({
            "company_name": company,
            "company_slug": analysis["company_slug"],
            "status": company_status,
            "checks": checks,
            "summary": {
                "local_evidence_count": len(records),
                "research_source_count": len(sources),
                "substantive_source_count": len(substantive_sources),
                "public_tool_attempt_count": len(public_tool_attempts),
                "failed_tool_attempt_count": len(failed_tool_attempts),
                "financial_tool_source_count": len(financial_sources),
                "missing_method_count": method_missing_count,
            },
        })
    quality_summary = shared_build_artifact_quality_report(
        [check for company in companies for check in company["checks"].values()]
    )
    overall_status = "passed" if quality_summary["status"] == "ok" else quality_summary["status"]
    return {
        "generated_at": utc_now_iso(),
        "status": overall_status,
        "passes_required_gate": overall_status != "failed",
        "privacy": "metadata_only_no_raw_prompts_no_raw_public_pages_no_document_text",
        "company_count": len(companies),
        "warning_check_count": quality_summary["warning_count"],
        "failed_check_count": quality_summary["failed_count"],
        "companies": companies,
    }

def research_source_status_counts(research_ledgers: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ledger in research_ledgers.values():
        for source in flattened_sources(ledger):
            status = str(source.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    return counts

def build_run_health_report(
    *,
    run_id: str,
    started_at: str,
    elapsed_ms: float,
    artifact_quality: dict[str, Any],
    observation_summary: dict[str, Any],
    action_ledger: dict[str, Any],
    knowledge_rag: dict[str, Any] | None,
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
    cache_policy_summary: dict[str, Any],
    actor_review_warnings: list[dict[str, Any]],
    actor_review_settings: dict[str, Any],
    llm_limiter: LlmCallLimiter,
) -> dict[str, Any]:
    source_status_counts = research_source_status_counts(research_ledgers)
    warning_source_count = sum(count for status, count in source_status_counts.items() if status in WARNING_SOURCE_STATUSES)
    failed_operation_count = int(observation_summary.get("failed_operation_count") or 0)
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not artifact_quality.get("passes_required_gate"):
        failures.append({"kind": "artifact_quality", "message": "Artifact quality gate failed."})
    elif artifact_quality.get("status") == "warning":
        warnings.append({"kind": "artifact_quality", "message": "Artifact quality completed with warnings."})
    if action_ledger.get("exhausted"):
        warnings.append({"kind": "action_budget", "message": "Action budget was exhausted before all optional calls could run."})
    if warning_source_count:
        warnings.append({"kind": "public_tools", "message": "One or more public tool/source attempts returned warning or failed statuses.", "count": warning_source_count})
    if failed_operation_count:
        warnings.append({"kind": "observability", "message": "Observed operations include failed metadata records.", "count": failed_operation_count})
    if actor_review_warnings:
        warnings.append({"kind": "actor_review", "message": "Actor review completed with warnings.", "count": len(actor_review_warnings)})
    rag_state = public_knowledge_rag_state(knowledge_rag or {})
    if knowledge_rag_is_required(knowledge_rag or {}) and rag_state.get("status") not in {"ready"}:
        failures.append({"kind": "knowledge_rag", "message": "Required RAG knowledge is not ready.", "status": rag_state.get("status")})
    status = "failed" if failures else ("warning" if warnings else "healthy")
    components = {
            "artifact_quality": {
                "status": artifact_quality.get("status"),
                "passes_required_gate": artifact_quality.get("passes_required_gate"),
                "warning_check_count": artifact_quality.get("warning_check_count"),
                "failed_check_count": artifact_quality.get("failed_check_count"),
            },
            "action_budget": {
                "budget": action_ledger.get("budget"),
                "used": action_ledger.get("used"),
                "remaining": action_ledger.get("remaining"),
                "exhausted": action_ledger.get("exhausted"),
            },
            "knowledge_rag": {
                "status": rag_state.get("status"),
                "required": knowledge_rag_is_required(knowledge_rag or {}),
                "indexed_count": (rag_state.get("index_summary") or {}).get("indexed_count") if isinstance(rag_state.get("index_summary"), dict) else None,
            },
            "public_tools": {
                "source_status_counts": source_status_counts,
                "warning_source_count": warning_source_count,
                "tool_operation_count": observation_summary.get("tool_operation_count"),
                "failed_operation_count": failed_operation_count,
            },
            "llm": {
                "llm_call_count": observation_summary.get("llm_call_count"),
                "limiter": llm_limiter.config_summary(),
            },
            "context_engine": {
                "actor_review_uses_context_engine": bool(actor_review_settings.get("use_context_engine")),
                "working_memory_persist_to_redis": bool(actor_review_settings.get("working_memory_persist_to_redis")),
                "boundary": "RAG knowledge may use Redis; working memory stays in local artifacts and compact prompt context.",
            },
            "cache_policy": {
                "force_reprocess": cache_policy_summary.get("force_reprocess"),
                "processed_company_count": cache_policy_summary.get("processed_company_count"),
                "skipped_company_count": cache_policy_summary.get("skipped_company_count"),
                "fresh_run": cache_policy_summary.get("fresh_run"),
            },
            "observability": {
                "trace_available": observation_summary.get("trace_available"),
                "record_count": observation_summary.get("record_count"),
                "failed_operation_count": failed_operation_count,
                "operation_counts": observation_summary.get("operation_counts"),
            },
    }
    return shared_build_run_health_report(
        components=components,
        warnings=warnings,
        failures=failures,
        status=status,
        elapsed_ms=round(elapsed_ms, 2),
        privacy="metadata_only_no_prompts_no_raw_rag_context_no_document_text_no_raw_public_pages",
        metadata={
            "run_id": run_id,
            "generated_at": utc_now_iso(),
            "started_at": started_at,
        },
        include_counts=False,
    )
