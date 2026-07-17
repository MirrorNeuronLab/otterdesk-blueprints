"""Cross-capability VC analysis and cache-hydration composition."""

from __future__ import annotations

from .common import *
from .evidence import build_company_evidence_layer, is_substantive_public_source
from .intake import load_cached_company_analysis, load_cached_research_ledger, slugify
from .knowledge import public_knowledge_rag_state
from .research_core import normalized_research_ledger
from .research_orchestration import reconcile_research
from .research_policy import build_adaptive_research_plan, build_fact_table
from .valuation import audit_method_scores

def build_company_analysis_from_method_scores(
    company: str,
    records: list[dict[str, Any]],
    research_ledger: dict[str, list[dict[str, Any]]],
    methods: dict[str, dict[str, Any]],
    fund_profile: str | None = None,
) -> dict[str, Any]:
    sources = [source for stage_sources in research_ledger.values() for source in stage_sources]
    facts = build_fact_table(company, records, sources)
    ordered_methods = {method_id: methods[method_id] for method_id in METHOD_IDS}
    audit = audit_method_scores(ordered_methods, facts)
    scored = [item["score"] for item in ordered_methods.values() if isinstance(item.get("score"), (int, float))]
    missing_methods = [method_id for method_id, method in ordered_methods.items() if method["status"] == "insufficient_evidence"]
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
        "method_count": len(ordered_methods),
        "methods": ordered_methods,
        "method_score_appendix": ordered_methods,
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
                "method_ids": [method_id for method_id, method in ordered_methods.items() if isinstance(method.get("score"), (int, float))],
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

def hydrate_cached_company_state(
    ctx: dict[str, Any],
    company_records: dict[str, list[dict[str, Any]]],
    company_work_queue: list[dict[str, Any]],
    knowledge_rag: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    store = ctx.get("state_store") or WorkflowStateStore(ctx["run_dir"])
    for item in company_work_queue:
        if item.get("status") != "unchanged_skipped":
            continue
        company = str(item["company_name"])
        cached_analysis = load_cached_company_analysis(ctx["output_folder"], company)
        cached_ledger = load_cached_research_ledger(ctx["output_folder"], company)
        if not cached_analysis or cached_ledger is None:
            item["status"] = "new_or_changed"
            item["cache_status"] = "missing_cached_report_reprocessed"
            item.setdefault("cache_policy", {})["freshness"] = "fresh_or_changed"
            item.setdefault("cache_policy", {})["decision"] = "process_company_packet"
            item.setdefault("cache_policy", {})["cache_source"] = ""
            continue
        records = company_records.get(company, [])
        reconciliation = cached_analysis.get("research_reconciliation") or reconcile_research(records, cached_ledger)
        cached_analysis["processing_status"] = "unchanged_skipped"
        cached_analysis["cached_from_previous_run"] = True
        cached_analysis["research_reconciliation"] = reconciliation
        cached_analysis["cache_policy"] = {
            **(item.get("cache_policy") or {}),
            "cache_source": "watch_state_and_company_artifacts",
            "freshness": "unchanged_cached",
            "decision": "reuse_cached_outputs",
        }
        if "research_plan" not in cached_analysis:
            internet = ctx["config"].get("internet_research") if isinstance(ctx["config"].get("internet_research"), dict) else {}
            cached_analysis["research_plan"] = build_adaptive_research_plan(company, records, internet)
        cached_analysis.setdefault("agent_tool_trace", [])
        cached_analysis.setdefault("research_plan", {}).setdefault("knowledge_rag", public_knowledge_rag_state(knowledge_rag))
        store.write_entity("analyses", str(cached_analysis["company_slug"]), cached_analysis)
        store.write_entity("research_ledgers", company, normalized_research_ledger(cached_ledger))
        store.write_entity("reconciliations", company, reconciliation)
        store.write_entity("method_scores", company, cached_analysis.get("methods") or {})
        store.write_entity("research_plans", company, cached_analysis.get("research_plan") or {})
        store.write_entity("agent_tool_traces", company, cached_analysis.get("agent_tool_trace") or [])
    return company_work_queue

