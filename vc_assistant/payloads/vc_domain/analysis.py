"""VC company-analysis composition and evidence summaries."""

from __future__ import annotations

from .common import *
from .evidence import build_company_evidence_layer, is_substantive_public_source
from .intake import slugify
from .research_policy import build_fact_table
from .valuation import audit_method_scores, score_company_methods

def build_company_analysis(
    company: str,
    records: list[dict[str, Any]],
    research_ledger: dict[str, list[dict[str, Any]]],
    scoring_workers: int = 1,
    fund_profile: str | None = None,
) -> dict[str, Any]:
    sources = [source for stage_sources in research_ledger.values() for source in stage_sources]
    facts = build_fact_table(company, records, sources)
    methods = score_company_methods(facts, max_workers=scoring_workers)
    audit = audit_method_scores(methods, facts)
    scored = [item["score"] for item in methods.values() if isinstance(item.get("score"), (int, float))]
    missing_methods = [method_id for method_id, method in methods.items() if method["status"] == "insufficient_evidence"]
    substantive_sources = [source for source in sources if is_substantive_public_source(source)]
    evidence_layer = build_company_evidence_layer(company, records, sources, fund_profile=fund_profile)
    evidence_summary_layer = evidence_layer["company_evidence_summary"]
    composite_score = evidence_summary_layer["investment_score"]
    method_average_score = round(sum(scored) / len(scored), 2) if scored else None
    return {
        "company_name": company,
        "company_slug": slugify(company),
        "composite_score": composite_score,
        "investment_score": composite_score,
        "method_average_score": method_average_score,
        "evidence_quality_score": evidence_summary_layer["evidence_quality_score"],
        "confidence_band": evidence_summary_layer["confidence_band"],
        "recommendation": evidence_summary_layer["recommendation"],
        "dimension_scores": evidence_summary_layer["dimension_scores"],
        "score_caps": evidence_summary_layer["score_caps"],
        "fund_profile": evidence_layer["fund_profile"],
        "method_count": len(methods),
        "methods": methods,
        "method_score_appendix": methods,
        "source_records": evidence_layer["source_records"],
        "evidence_items": evidence_layer["evidence_items"],
        "claim_records": evidence_layer["claim_records"],
        "evidence_graph": evidence_layer["evidence_graph"],
        "company_evidence_summary": evidence_summary_layer,
        "truth_discovery": evidence_layer.get("truth_discovery", {}),
        "bayesian_claim_explanations": evidence_layer.get("bayesian_claim_explanations", []),
        "fact_table": facts,
        "audit": audit,
        "evidence_summary": {
            "document_count": len(records),
            "source_count": len(sources),
            "substantive_source_count": len(substantive_sources),
            "financial_tool_source_count": len([source for source in sources if source.get("skill") == "financial_public_data_tool"]),
            "missing_methods": missing_methods,
            "composite_score_evidence": {
                "status": "scored" if composite_score is not None else "insufficient_evidence",
                "scored_method_count": len(scored),
                "method_ids": [method_id for method_id, method in methods.items() if isinstance(method.get("score"), (int, float))],
                "reason": "Composite is the confidence-weighted investment score from normalized claims; method scores are retained as an appendix." if composite_score is not None else "No normalized claim evidence was available for a numeric score.",
                "method_average_score": method_average_score,
                "evidence_quality_score": evidence_summary_layer["evidence_quality_score"],
                "confidence_band": evidence_summary_layer["confidence_band"],
                "fund_profile": evidence_layer["fund_profile"],
                "truth_discovery_eligible_claim_count": len((evidence_layer.get("truth_discovery") or {}).get("eligible_claim_ids") or []),
                "bayesian_claim_explanation_count": len(evidence_layer.get("bayesian_claim_explanations") or []),
            },
        },
        "result_evidence": {
            "composite_score": {
                "value": composite_score,
                "why": "Confidence-weighted normalized claims by fund profile, with hard caps for missing team, traction, product, or evidence quality." if composite_score is not None else "No scored normalized claims were available.",
                "evidence_refs": sorted({ev.get("evidence_id") for ev in evidence_layer["evidence_items"] if ev.get("evidence_id")})[:20],
                "missing_evidence": dedupe_list(
                    [
                        missing
                        for claim in evidence_layer["claim_records"]
                        for missing in (claim.get("required_next_evidence") or [])[:2]
                        if int(claim.get("net_confidence") or 0) < 70
                    ],
                    20,
                ),
                "score_caps": evidence_summary_layer["score_caps"],
            },
            "research": {
                "source_count": len(sources),
                "substantive_source_count": len(substantive_sources),
                "budget_or_source_warnings": [source.get("warning") for source in sources if source.get("warning")],
            },
        },
        "decision_policy": "report_only_user_decides",
    }

def score_company(company: str, records: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    return build_company_analysis(company, records, {"legacy_research": sources})

def warnings_for_company(analysis: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    for source in sources:
        if source.get("warning") or source.get("status") in WARNING_SOURCE_STATUSES:
            warnings.append({
                "kind": "research",
                "status": source.get("status"),
                "source": source.get("url"),
                "message": source.get("warning") or source.get("snippet"),
            })
    for method in analysis["methods"].values():
        for warning in method.get("warnings") or []:
            warnings.append({"kind": "method", "method_id": method["method_id"], "message": warning})
    for finding in analysis["audit"].get("findings") or []:
        warnings.append({"kind": "audit", **finding})
    return warnings

def research_gap_followups(analysis: dict[str, Any], sources: list[dict[str, Any]]) -> list[str]:
    followups = []
    plan = analysis.get("research_plan") or {}
    for lane in plan.get("lanes") or []:
        followups.append(f"Review {lane.get('lane_id')}: {lane.get('reason')}")
    reconciliation = analysis.get("research_reconciliation") or {}
    for missing in reconciliation.get("missing_public_evidence") or []:
        topic = missing.get("topic") or "public evidence"
        followups.append(f"Find public confirmation for local {topic} claims.")
    for method_id in analysis.get("evidence_summary", {}).get("missing_methods", []):
        followups.append(f"Add stronger evidence for {method_id.replace('_', ' ')} before relying on its score.")
    for source in sources:
        if source.get("status") in WARNING_SOURCE_STATUSES:
            followups.append(f"Revisit {source.get('verification_target')}: {source.get('warning') or source.get('snippet')}")
    return dedupe_list(followups, 12)

def summarize_local_evidence(records: list[dict[str, Any]], *, limit: int = 8) -> dict[str, Any]:
    readable_records = [
        record
        for record in records
        if int(record.get("character_count") or 0) > 0 and not record.get("ocr_required")
    ]
    return {
        "record_count": len(records),
        "readable_record_count": len(readable_records),
        "total_character_count": sum(int(record.get("character_count") or 0) for record in records),
        "files": [
            {
                "filename": record.get("filename"),
                "suffix": record.get("suffix"),
                "sha256_prefix": str(record.get("sha256") or "")[:12],
                "character_count": record.get("character_count"),
                "extraction_method": record.get("extraction_method"),
                "warning_count": len(record.get("warnings") or []),
            }
            for record in records[:limit]
        ],
    }

def summarize_research_sources(sources: list[dict[str, Any]], *, limit: int = 12) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    for source in sources:
        status = str(source.get("status") or "unknown")
        quality = str(source.get("source_quality_label") or "thin_signal")
        target = str(source.get("verification_target") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        target_counts[target] = target_counts.get(target, 0) + 1
    substantive = [source for source in sources if is_substantive_public_source(source)]
    return {
        "source_count": len(sources),
        "substantive_source_count": len(substantive),
        "status_counts": status_counts,
        "source_quality_counts": quality_counts,
        "verification_target_counts": target_counts,
        "sample_sources": [
            {
                "title": source.get("title"),
                "url": source.get("url"),
                "status": source.get("status"),
                "source_quality_label": source.get("source_quality_label"),
                "verification_target": source.get("verification_target"),
                "warning": source.get("warning"),
            }
            for source in sources[:limit]
        ],
    }

def build_company_evidence_summaries(
    analyses: list[dict[str, Any]],
    company_records: dict[str, list[dict[str, Any]]],
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    summaries = []
    for analysis in analyses:
        company = analysis["company_name"]
        sources = flattened_sources(research_ledgers.get(company, {}))
        summaries.append(
            {
                "company_name": company,
                "company_slug": analysis["company_slug"],
                "investment_score": analysis.get("investment_score"),
                "evidence_quality_score": analysis.get("evidence_quality_score"),
                "confidence_band": analysis.get("confidence_band"),
                "recommendation": analysis.get("recommendation"),
                "claim_count": len(analysis.get("claim_records") or []),
                "normalized_evidence_count": len(analysis.get("evidence_items") or []),
                "local_evidence": summarize_local_evidence(company_records.get(company, []), limit=5),
                "research_sources": summarize_research_sources(sources, limit=8),
                "missing_methods": (analysis.get("evidence_summary") or {}).get("missing_methods", []),
            }
        )
    return summaries

