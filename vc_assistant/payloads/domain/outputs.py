"""VC report artifact composition and cache-aware output writing."""

from __future__ import annotations

from .common import *
from .analysis import summarize_local_evidence, summarize_research_sources, warnings_for_company
from .intake import build_cache_policy_summary
from .reporting import build_method_coverage, build_research_coverage, render_markdown
from .research_core import (
    compact_company_report_for_transport,
    compact_local_evidence_for_transport,
    compact_research_sources_for_transport,
)

def final_artifact_for_transport(final_artifact: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded artifact shape printed to the runtime workflow chain."""
    compact = dict(final_artifact)
    compact.pop("research_sources", None)
    compact.pop("evidence", None)
    reports = compact.get("company_reports")
    if isinstance(reports, list):
        compact["company_reports"] = [
            compact_company_report_for_transport(report) if isinstance(report, dict) else report
            for report in reports
        ]
    ledger = compact.get("action_ledger")
    if isinstance(ledger, dict):
        compact["action_ledger"] = {key: value for key, value in ledger.items() if key != "actions"}
    compact["transport"] = {
        "compacted": True,
        "omitted_fields": ["top_level.research_sources", "top_level.evidence", "action_ledger.actions"],
        "reason": "Prevent repeated workflow handoff payloads from growing Redis job state; detailed per-company artifacts remain in output files.",
    }
    return compact

def render_run_summary(analyses: list[dict[str, Any]], queue: list[dict[str, Any]], research_coverage: dict[str, Any], method_coverage: dict[str, Any]) -> str:
    skipped_count = sum(1 for item in queue if item["status"] == "unchanged_skipped")
    processed_count = len(queue) - skipped_count
    force_reprocess = any(bool((item.get("cache_policy") or {}).get("force_reprocess")) for item in queue)
    lines = [
        "# VC Assistant Run Summary",
        "",
        "Report-only run. The user decides what to review next.",
        "",
        f"Companies in index: {len(analyses)}",
        f"Companies processed this cycle: {processed_count}",
        f"Unchanged companies skipped: {skipped_count}",
        f"Force reprocess: {force_reprocess}",
        "",
        "## Cache Policy",
    ]
    for item in queue:
        policy = item.get("cache_policy") if isinstance(item.get("cache_policy"), dict) else {}
        lines.append(
            f"- {item['company_name']}: {policy.get('freshness') or item['status']} "
            f"({policy.get('decision') or item['status']}; previous_run_id: {policy.get('previous_run_id') or 'none'})"
        )
    lines += [
        "",
        "## Company Scores",
    ]
    for analysis in analyses:
        lines.append(
            f"- {analysis['company_name']}: investment score {analysis.get('investment_score')} "
            f"(evidence quality {analysis.get('evidence_quality_score')}, {str(analysis.get('confidence_band') or 'not_reliable').replace('_', ' ')})"
        )
    lines += ["", "## Research Coverage"]
    for item in research_coverage["companies"]:
        lines.append(f"- {item['company_name']}: {item['agent_counts']}")
    lines += ["", "## Method Coverage"]
    for item in method_coverage["companies"]:
        lines.append(f"- {item['company_name']}: {item['method_statuses']}")
    return "\n".join(lines) + "\n"

def write_company_outputs(
    output_folder: Path,
    analyses: list[dict[str, Any]],
    company_records: dict[str, list[dict[str, Any]]],
    research_ledgers: dict[str, dict[str, list[dict[str, Any]]]],
    queue: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output_files = []
    queue_by_slug = {item["company_slug"]: item for item in queue}
    for analysis in analyses:
        slug = analysis["company_slug"]
        company_dir = output_folder / slug
        evidence = company_records[analysis["company_name"]]
        research_ledger = research_ledgers[analysis["company_name"]]
        sources = flattened_sources(research_ledger)
        warnings = warnings_for_company(analysis, sources)
        analysis["local_evidence_summary"] = summarize_local_evidence(evidence)
        analysis["research_source_summary"] = summarize_research_sources(sources)
        analysis["evidence_artifacts"] = {
            "local_evidence_path": str(company_dir / "evidence.json"),
            "research_sources_path": str(company_dir / "research_sources.json"),
            "research_ledger_path": str(output_folder / "research_ledgers" / f"{slug}.json"),
            "source_records_path": str(company_dir / "source_records.json"),
            "evidence_items_path": str(company_dir / "evidence_items.json"),
            "claim_records_path": str(company_dir / "claims.json"),
            "evidence_graph_path": str(company_dir / "evidence_graph.json"),
            "bayesian_claim_explanations_path": str(company_dir / "bayesian_claim_explanations.json"),
        }
        analysis["evidence"] = compact_local_evidence_for_transport(evidence)
        analysis["research_sources"] = compact_research_sources_for_transport(sources)
        analysis["warnings"] = warnings
        write_json(company_dir / "analysis.json", analysis)
        write_json(company_dir / "method_scores.json", analysis["methods"])
        write_json(company_dir / "research_plan.json", analysis.get("research_plan") or {})
        write_json(company_dir / "agent_tool_trace.json", analysis.get("agent_tool_trace") or [])
        write_json(company_dir / "research_sources.json", sources)
        write_json(company_dir / "sources.json", sources)
        write_json(company_dir / "evidence.json", evidence)
        write_json(company_dir / "source_records.json", analysis.get("source_records") or [])
        write_json(company_dir / "evidence_items.json", analysis.get("evidence_items") or [])
        write_json(company_dir / "claims.json", analysis.get("claim_records") or [])
        write_json(company_dir / "evidence_graph.json", analysis.get("evidence_graph") or {})
        write_json(company_dir / "bayesian_claim_explanations.json", analysis.get("bayesian_claim_explanations") or [])
        write_json(company_dir / "warnings.json", warnings)
        markdown = render_markdown(analysis, sources, evidence)
        (company_dir / "analysis.md").write_text(markdown, encoding="utf-8")
        for name in ("analysis.json", "analysis.md", "method_scores.json", "research_plan.json", "agent_tool_trace.json", "research_sources.json", "sources.json", "evidence.json", "source_records.json", "evidence_items.json", "claims.json", "evidence_graph.json", "bayesian_claim_explanations.json", "warnings.json"):
            output_files.append({"kind": name.rsplit(".", 1)[0], "path": str(company_dir / name), "company": analysis["company_name"]})
        write_json(output_folder / "company_fact_tables" / f"{slug}.json", analysis["fact_table"])
        write_json(output_folder / "research_ledgers" / f"{slug}.json", research_ledger)
        write_json(output_folder / "method_scores" / f"{slug}.json", analysis["methods"])
        write_json(output_folder / "audit_findings" / f"{slug}.json", analysis["audit"])
        write_json(output_folder / "evidence_items" / f"{slug}.json", analysis.get("evidence_items") or [])
        write_json(output_folder / "claim_records" / f"{slug}.json", analysis.get("claim_records") or [])
    index = {
        "blueprint_id": BLUEPRINT_ID,
        "generated_at": utc_now_iso(),
        "report_only": True,
        "cache_policy": build_cache_policy_summary(
            queue,
            processed_company_names=[item["company_name"] for item in queue if item["status"] != "unchanged_skipped"],
            skipped_company_names=[item["company_name"] for item in queue if item["status"] == "unchanged_skipped"],
        ),
        "companies": [
            {
                "company_name": analysis["company_name"],
                "company_slug": analysis["company_slug"],
                "composite_score": analysis["composite_score"],
                "investment_score": analysis.get("investment_score"),
                "evidence_quality_score": analysis.get("evidence_quality_score"),
                "confidence_band": analysis.get("confidence_band"),
                "recommendation": analysis.get("recommendation"),
                "missing_methods": analysis["evidence_summary"]["missing_methods"],
                "processing_status": analysis.get("processing_status"),
                "cached_from_previous_run": bool(analysis.get("cached_from_previous_run")),
                "cache_policy": analysis.get("cache_policy") or (queue_by_slug.get(analysis["company_slug"]) or {}).get("cache_policy"),
            }
            for analysis in analyses
        ],
    }
    research_coverage = build_research_coverage(research_ledgers)
    method_coverage = build_method_coverage(analyses)
    write_json(output_folder / "company_index.json", index)
    write_json(output_folder / "company_work_queue.json", queue)
    write_json(output_folder / "research_coverage.json", research_coverage)
    write_json(output_folder / "method_coverage.json", method_coverage)
    index_lines = ["# VC Heuristic Company Index", "", "Report-only score summaries. The user decides what to do next.", ""]
    for item in index["companies"]:
        policy = item.get("cache_policy") if isinstance(item.get("cache_policy"), dict) else {}
        index_lines.append(
            f"- {item['company_name']}: investment score {item.get('investment_score')} "
            f"(evidence quality {item.get('evidence_quality_score')}, {str(item.get('confidence_band') or 'not_reliable').replace('_', ' ')}) "
            f"({policy.get('freshness') or item.get('processing_status')})"
        )
    (output_folder / "company_index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    (output_folder / "run_summary.md").write_text(render_run_summary(analyses, queue, research_coverage, method_coverage), encoding="utf-8")
    output_files.extend([
        {"kind": "company_index_json", "path": str(output_folder / "company_index.json")},
        {"kind": "company_index_markdown", "path": str(output_folder / "company_index.md")},
        {"kind": "company_work_queue", "path": str(output_folder / "company_work_queue.json")},
        {"kind": "research_coverage", "path": str(output_folder / "research_coverage.json")},
        {"kind": "method_coverage", "path": str(output_folder / "method_coverage.json")},
        {"kind": "run_summary_markdown", "path": str(output_folder / "run_summary.md")},
    ])
    return output_files
