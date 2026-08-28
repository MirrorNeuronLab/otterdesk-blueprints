"""Purchase decision-packet composition and durable customer outputs."""

from __future__ import annotations

import json
import os
import re
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
from .llm_analysis import (
    analysis_settings,
    analysis_validation_context,
    candidate_analysis_packet,
    generate_structured_analysis,
    known_source_refs,
    validate_report_narrative,
)
from .state import _inputs, _save, _state


def build_final_artifact(inputs: dict[str, Any], evidence: dict[str, Any], recommendation: dict[str, Any], rag: dict[str, Any], sources: list[dict[str, Any]], warnings: list[dict[str, Any]], documents: list[dict[str, Any]], actor_findings: dict[str, Any], run_id: str, intake_plan: dict[str, Any] | None = None, request: dict[str, Any] | None = None) -> dict[str, Any]:
    source_refs = list(dict.fromkeys(["inputs.json", "events.jsonl", "result.json", *(evidence.get("source_refs") or []), *(rag.get("citations") or []), *(item.get("source_ref") for item in sources if item.get("source_ref"))]))
    item_description = str(inputs.get("item_description") or "unspecified item").rstrip(".")
    return {
        "type": OUTPUT_TYPE,
        "schema_version": "mn.blueprint.purchasing_manager.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "review_ready",
        "purchase_type": inputs.get("purchase_type"),
        "item_description": inputs.get("item_description"),
        "executive_summary": f"Research packet for {inputs.get('purchase_type')} purchase: {item_description}. Recommendation: {recommendation.get('label')} with {recommendation.get('confidence')} confidence.",
        "recommended_action": recommendation.get("label"),
        "confidence": recommendation.get("confidence"),
        "recommendation_rationale": recommendation.get("rationale"),
        "intake_plan": intake_plan or {},
        "request_source": request or {},
        "research_leads": list((request or {}).get("research_links") or []),
        "evidence": {"deterministic": evidence, "documents": [{key: value for key, value in item.items() if key != "text"} for item in documents], "public_sources": sources},
        "risk_flags": recommendation.get("risk_flags") or [],
        "evidence_gaps": recommendation.get("evidence_gaps") or [],
        "knowledge_rag": {key: value for key, value in rag.items() if key not in {"_rag_config"}},
        "actor_findings": actor_findings,
        "warnings": warnings,
        "next_steps": [
            "Refresh the preferred listing and request a written, all-in business quote for the exact configuration.",
            "Replace planning assumptions with approved company inputs and rerun low, base, and stress cases.",
            "Obtain technical-owner and procurement approval before issuing a purchase order or other commitment.",
        ],
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
        {"step": "supplier_comparison_and_tco", "status": "completed", "candidate_count": len(final_artifact.get("candidate_comparisons") or [])},
        {"step": "recommendation_audit", "status": "completed", "label": final_artifact.get("recommended_action"), "confidence": final_artifact.get("confidence")},
        {"step": "human_review_gate", "status": "blocked_pending_review", "blocked_actions": BLOCKED_ACTIONS},
    ]
    final_artifact["artifact_quality"] = quality
    final_artifact["run_health"] = health
    final_artifact["action_ledger"] = ledger
    evidence = final_artifact.get("evidence") or {}
    paths = {
        "purchasing_manager_json": output_dir / "purchasing_manager.json",
        "report_markdown": output_dir / "purchasing_manager_report.md",
        "evidence_json": output_dir / "evidence.json",
        "research_sources_json": output_dir / "research_sources.json",
        "knowledge_rag_json": output_dir / "knowledge_rag.json",
        "action_ledger_json": output_dir / "action_ledger.json",
        "artifact_quality_json": output_dir / "artifact_quality.json",
        "run_health_json": output_dir / "run_health.json",
    }
    output_files = [{"kind": kind, "path": str(path)} for kind, path in paths.items()]
    final_artifact["output_files"] = output_files
    paths["purchasing_manager_json"].write_text(json.dumps(final_artifact, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
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
        {"name": "candidate_comparison_present", "passed": bool(final_artifact.get("candidate_comparisons"))},
        {"name": "procurement_summary_present", "passed": isinstance(final_artifact.get("procurement_summary"), dict)},
        {"name": "llm_generation_provenance_present", "passed": isinstance(final_artifact.get("llm_generation"), dict)},
        {"name": "report_narrative_present", "passed": isinstance(final_artifact.get("report_narrative"), dict)},
    ]
    passed = all(item["passed"] for item in checks)
    return {"schema_version": "mn.blueprint.artifact_quality.v1", "status": "usable_with_review" if passed else "usable_with_review_warnings", "review_required": True, "quality_checks": checks, "warnings": final_artifact.get("warnings") or []}


def build_procurement_summary(
    inputs: dict[str, Any], comparisons: list[dict[str, Any]], preferred_candidate: str | None
) -> dict[str, Any]:
    preferred = next(
        (
            item
            for item in comparisons
            if item.get("candidate_id") == preferred_candidate
        ),
        None,
    )
    tco = (preferred or {}).get("tco") or {}
    landed_acquisition_cost = tco.get(
        "landed_acquisition_cost", (preferred or {}).get("known_upfront_cost")
    )
    budget = inputs.get("budget")
    budget_amount = _currency_amount(budget)
    budget_status = "not_set"
    if budget_amount is not None:
        budget_status = (
            "within_budget"
            if landed_acquisition_cost is not None
            and landed_acquisition_cost <= budget_amount
            else "over_budget_or_unverified"
        )
    scenarios = list((preferred or {}).get("scenario_analysis") or [])
    scenario_values = [
        _currency_amount(item.get("risk_adjusted_npv_tco"))
        for item in scenarios
        if _currency_amount(item.get("risk_adjusted_npv_tco")) is not None
    ]
    return {
        "decision_status": "source_refresh_and_human_approval_required",
        "budget": budget,
        "budget_status": budget_status,
        "preferred_candidate": preferred_candidate,
        "preferred_vendor": (preferred or {}).get("vendor"),
        "observed_base_price": tco.get("base_purchase_price"),
        "vendor_cash_cost": tco.get("vendor_cash_cost"),
        "landed_acquisition_cost": landed_acquisition_cost,
        "landed_budget_headroom": round(budget_amount - landed_acquisition_cost, 2)
        if budget_amount is not None and landed_acquisition_cost is not None
        else None,
        "known_upfront_cost": landed_acquisition_cost,
        "known_three_year_cost": (preferred or {}).get("known_three_year_cost"),
        "financial_npv_tco": tco.get("financial_npv_tco"),
        "risk_adjusted_npv_tco": tco.get("risk_adjusted_npv_tco"),
        "equivalent_annual_cost": tco.get("equivalent_annual_cost"),
        "risk_adjusted_cost_per_productive_hour": tco.get(
            "risk_adjusted_cost_per_productive_hour"
        ),
        "scenario_risk_adjusted_npv_low": min(scenario_values)
        if scenario_values
        else None,
        "scenario_risk_adjusted_npv_high": max(scenario_values)
        if scenario_values
        else None,
        "hard_constraints_passed": (preferred or {}).get("hard_constraints_passed"),
        "observed_at": (preferred or {}).get("observed_at"),
        "availability_status": (preferred or {}).get("availability_status"),
        "lead_time_business_days": (preferred or {}).get("lead_time_business_days"),
        "approval_checklist": [
            "Reopen every supplier source and confirm current price, stock, exact SKU/configuration, tax, fulfillment cost, and delivery date.",
            "Obtain a written business quote; a public listing is not a reserved price or inventory commitment.",
            "Confirm the exact configuration against technical requirements and obtain the technical owner's sign-off.",
            "Replace utilization, labor, downtime, maintenance, discount-rate, energy, and residual-value planning assumptions with approved company values.",
            "Confirm supplier warranty, return process, fulfillment responsibility, and support escalation path.",
            "Compare cash, financing, leasing, or rental only after complete, eligible transaction terms have been sourced.",
            "Obtain procurement approval before issuing a purchase order or making any commitment.",
        ],
    }


def _currency(value: Any) -> str:
    amount = _currency_amount(value)
    return f"${amount:,.2f}" if amount is not None else "Not quoted"


def _percent(value: Any) -> str:
    amount = _currency_amount(value)
    return f"{amount * 100:.2f}%" if amount is not None else "Not set"


def _unit_rate(value: Any) -> str:
    amount = _currency_amount(value)
    return f"${amount:.4f}" if amount is not None else "Not set"


def _business_days(value: Any) -> str:
    amount = _currency_amount(value)
    if amount is None:
        return "Verify with supplier"
    number = str(int(amount)) if amount.is_integer() else str(amount)
    return f"{number} business {'day' if amount == 1 else 'days'}"


def _display_number(value: Any) -> str:
    amount = _currency_amount(value)
    if amount is None:
        return "Verify"
    return str(int(amount)) if amount.is_integer() else str(amount)


def _currency_amount(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
        return float(match.group(0).replace(",", "")) if match else None


def render_markdown(artifact: dict[str, Any]) -> str:
    evidence = artifact.get("evidence") or {}
    intake_plan = artifact.get("intake_plan") or {}
    procurement = artifact.get("procurement_summary") or {}
    comparisons = artifact.get("candidate_comparisons") or []
    preferred = next(
        (
            item
            for item in comparisons
            if item.get("candidate_id") == artifact.get("preferred_candidate")
        ),
        {},
    )
    preferred_tco = preferred.get("tco") or {}
    methodology = preferred.get("tco_methodology") or {}
    generation = artifact.get("llm_generation") or {}
    narrative = artifact.get("report_narrative") or {}
    analysis_interpretation = artifact.get("analysis_interpretation") or {}
    risk_interpretation = artifact.get("risk_interpretation") or {}
    decision_analysis = artifact.get("decision_analysis") or {}
    lines = [
        "# Purchasing Manager Report",
        "",
        f"**Purchase type:** {artifact.get('purchase_type')}",
        f"**Item or trip:** {artifact.get('item_description') or 'Not specified'}",
        f"**Recommendation:** {artifact.get('recommended_action')}",
        f"**Confidence:** {artifact.get('confidence')}",
        f"**LLM narrative status:** {generation.get('status') or 'not available'}",
        "",
        "## Executive Summary",
        str(narrative.get("executive_summary") or artifact.get("executive_summary") or ""),
        "",
        "## Decision Rationale",
        str(narrative.get("decision_rationale") or artifact.get("recommendation_rationale") or ""),
        "",
        "## Procurement Decision Summary",
        f"- Decision status: {procurement.get('decision_status') or 'human_review_required'}",
        f"- Preferred option: {procurement.get('preferred_candidate') or 'No eligible option'}",
        f"- Preferred supplier: {procurement.get('preferred_vendor') or 'Not identified'}",
        f"- Budget status: {procurement.get('budget_status') or 'not_set'}",
        f"- Observed base price: {_currency(procurement.get('observed_base_price'))}",
        f"- Landed acquisition cost: {_currency(procurement.get('landed_acquisition_cost'))}",
        f"- Landed-budget headroom: {_currency(procurement.get('landed_budget_headroom'))}",
        f"- Financial NPV TCO: {_currency(procurement.get('financial_npv_tco'))}",
        f"- Risk-adjusted NPV TCO: {_currency(procurement.get('risk_adjusted_npv_tco'))}",
        f"- Risk-adjusted equivalent annual cost: {_currency(procurement.get('equivalent_annual_cost'))}",
        f"- Risk-adjusted cost per productive hour: {_currency(procurement.get('risk_adjusted_cost_per_productive_hour'))}",
        f"- Scenario range, risk-adjusted NPV: {_currency(procurement.get('scenario_risk_adjusted_npv_low'))} to {_currency(procurement.get('scenario_risk_adjusted_npv_high'))}",
        f"- Source observed: {procurement.get('observed_at') or 'Timestamp missing'}",
        f"- Availability: {procurement.get('availability_status') or 'Verify with supplier'}",
        f"- Lead time: {_business_days(procurement.get('lead_time_business_days'))}",
    ]
    if generation.get("status") == "completed_with_fallback":
        lines.extend(
            [
                "",
                "> **LLM fallback warning:** One or more narrative sections used deterministic fallback text because model output was unavailable or failed validation. Numerical tables, hard gates, and rankings were not affected.",
            ]
        )
    lines.extend(
        [
            "",
            "## Financial Interpretation",
            str(narrative.get("financial_interpretation") or analysis_interpretation.get("summary") or "Deterministic tables are authoritative."),
            "",
            "## Risk Interpretation",
            str(narrative.get("risk_interpretation") or risk_interpretation.get("overall_posture") or "See deterministic risk flags."),
            "",
            "## Candidate Comparison",
            "| Option | Supplier | Observed price | Landed cost | Financial NPV | Risk-adjusted NPV | Risk-adjusted EAC | Hard gate |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for candidate in comparisons:
        lines.append(
            "| {label} | {vendor} | {price} | {landed} | {financial} | {risk} | {eac} | {constraints} |".format(
                label=candidate.get("label") or candidate.get("candidate_id"),
                vendor=candidate.get("vendor") or "Not identified",
                price=_currency((candidate.get("tco") or {}).get("base_purchase_price")),
                landed=_currency((candidate.get("tco") or {}).get("landed_acquisition_cost")),
                financial=_currency((candidate.get("tco") or {}).get("financial_npv_tco")),
                risk=_currency((candidate.get("tco") or {}).get("risk_adjusted_npv_tco")),
                eac=_currency((candidate.get("tco") or {}).get("equivalent_annual_cost")),
                constraints="Pass" if candidate.get("hard_constraints_passed") else "Does not pass",
            )
        )
    alternative_tradeoffs = narrative.get("alternative_tradeoffs") or decision_analysis.get("why_not_alternatives") or []
    if alternative_tradeoffs:
        lines.extend(["", "## Alternative Tradeoffs"])
        for item in alternative_tradeoffs:
            if isinstance(item, dict):
                lines.append(
                    f"- **{item.get('candidate_id') or 'Portfolio'}:** {item.get('interpretation') or item.get('explanation') or 'See deterministic comparison.'}"
                )
    negotiation_points = narrative.get("negotiation_points") or risk_interpretation.get("negotiation_points") or []
    if negotiation_points:
        lines.extend(["", "## Negotiation Points"])
        lines.extend(f"- {item}" for item in negotiation_points)
    narrative_conditions = narrative.get("approval_conditions") or decision_analysis.get("approval_conditions") or []
    if narrative_conditions:
        lines.extend(["", "## Narrative Approval Conditions"])
        lines.extend(f"- {item}" for item in narrative_conditions)
    if not comparisons:
        lines.append("| No structured options supplied | — | — | — | — | — | — | — |")
    if preferred:
        lines.extend(
            [
                "",
                "## Preferred Option Lifecycle Cost Analysis",
                f"- Model completeness: {str(preferred_tco.get('model_status') or 'Not assessed').replace('_', ' ')}",
                f"- Vendor cash cost, including estimated tax: {_currency(preferred_tco.get('vendor_cash_cost'))}",
                f"- Internal implementation: {_currency(preferred_tco.get('internal_implementation_cost'))} ({_display_number(preferred_tco.get('internal_labor_hours'))} hours)",
                f"- Planned annual energy: {_display_number(preferred_tco.get('annual_energy_kwh'))} kWh / {_currency(preferred_tco.get('annual_energy_cost'))}",
                f"- Power planning inputs: {_display_number(preferred_tco.get('active_power_watts'))} W active component envelope and {_display_number(preferred_tco.get('idle_power_watts'))} W idle",
                f"- Power evidence status: {preferred_tco.get('power_measurement_status') or 'No measurement status supplied'}",
                f"- Annual financial operating cost: {_currency(preferred_tco.get('annual_financial_operating_cost'))}",
                f"- Annual downtime exposure: {_currency(preferred_tco.get('annual_downtime_exposure'))}",
                f"- Expected year-{methodology.get('horizon_years') or 3} residual value: {_currency(preferred_tco.get('residual_value'))}",
                f"- Undiscounted lifecycle cost: {_currency(preferred_tco.get('undiscounted_lifecycle_cost'))}",
                f"- Excluded or unpriced items: {', '.join(preferred_tco.get('excluded_or_unpriced_costs') or []) or 'None recorded'}",
                "",
                "### Planning Assumptions",
                f"- Horizon: {methodology.get('horizon_years') or 'Not set'} years; annual discount rate: {_percent(methodology.get('discount_rate'))}",
                f"- Sales-tax rate: {_percent(methodology.get('tax_rate'))}; electricity: {_unit_rate(methodology.get('electricity_rate_per_kwh'))}/kWh",
                f"- Utilization: {_display_number(methodology.get('active_hours_per_year'))} active plus {_display_number(methodology.get('idle_hours_per_year'))} idle hours/year",
                f"- Loaded labor: {_currency(methodology.get('loaded_labor_cost_per_hour'))}/hour; downtime: {_currency(methodology.get('downtime_cost_per_hour'))}/hour for {_display_number(methodology.get('expected_downtime_hours_per_year'))} hours/year",
                f"- Maintenance reserve: {_currency(methodology.get('annual_maintenance_reserve'))}/year; residual: {_percent(methodology.get('residual_value_percent'))} of observed base price",
                f"- Methods applied: {', '.join(methodology.get('methods') or [])}",
            ]
        )
        lines.extend(["", "### Scenario Sensitivity", "| Scenario | Financial NPV | Risk-adjusted NPV | Risk-adjusted EAC | Energy/year | Downtime/year | Residual |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for scenario in preferred.get("scenario_analysis") or []:
            lines.append(
                "| {name} | {financial} | {risk} | {eac} | {energy} | {downtime} | {residual} |".format(
                    name=scenario.get("name"),
                    financial=_currency(scenario.get("financial_npv_tco")),
                    risk=_currency(scenario.get("risk_adjusted_npv_tco")),
                    eac=_currency(scenario.get("equivalent_annual_cost")),
                    energy=_currency(scenario.get("annual_energy_cost")),
                    downtime=_currency(scenario.get("annual_downtime_exposure")),
                    residual=_currency(scenario.get("residual_value")),
                )
            )
        lines.extend(["", "### Acquisition Funding Method Analysis", "Funding-method amounts cover the supplier cash cost. Internal deployment and lifecycle costs remain outside this table and apply according to the selected structure.", "", "| Method | Status | Monthly payment | Nominal cash outflow | Present-value cost | Incremental PV vs cash |", "| --- | --- | ---: | ---: | ---: | ---: |"])
        for method in preferred.get("acquisition_method_analysis") or []:
            missing = ", ".join(method.get("missing_terms") or [])
            status = method.get("status") or "unknown"
            if missing:
                status = f"{status}: {missing}"
            lines.append(
                "| {method} | {status} | {monthly} | {nominal} | {pv} | {incremental} |".format(
                    method=method.get("method"),
                    status=status,
                    monthly=_currency(method.get("monthly_payment")),
                    nominal=_currency(method.get("nominal_cash_outflow")),
                    pv=_currency(method.get("present_value_cost")),
                    incremental=_currency(method.get("incremental_present_value_vs_cash")),
                )
            )
    lines.extend([
        "",
        "## Purchase Decision Frame",
        f"- Goal: {intake_plan.get('normalized_goal') or 'Not specified'}",
        f"- Criteria: {', '.join(intake_plan.get('decision_criteria') or []) or 'Not specified'}",
        f"- Unknowns: {', '.join(intake_plan.get('unknowns') or []) or 'None recorded.'}",
        "",
        "## Deterministic Evidence",
        f"- Documents reviewed: {evidence.get('deterministic', {}).get('document_count', 0)}",
        f"- Live public-source refreshes completed in this run: {evidence.get('deterministic', {}).get('public_source_count', 0)}",
        f"- {evidence.get('deterministic', {}).get('price_evidence_label') or 'Observed prices'}: {evidence.get('deterministic', {}).get('observed_price_values') or 'Unknown'}",
        "",
        "## Risk Flags",
    ])
    lines.extend(f"- {item}" for item in artifact.get("risk_flags") or ["None recorded by deterministic checks."])
    lines.extend(["", "## Evidence Gaps"])
    lines.extend(f"- {item}" for item in artifact.get("evidence_gaps") or ["None recorded."])
    lines.extend(["", "## Sources"])
    lines.extend(f"- {item}" for item in artifact.get("source_refs") or ["No source references recorded."])
    lines.extend(["", "## Next Steps"])
    lines.extend(f"- {item}" for item in artifact.get("next_steps") or [])
    lines.extend(["", "## Approval Checklist"])
    lines.extend(f"- {item}" for item in procurement.get("approval_checklist") or [])
    lines.extend(["", "## Review Boundary"])
    lines.extend(f"- Do not: {item}" for item in (artifact.get("review_boundary") or {}).get("blocked_actions") or BLOCKED_ACTIONS)
    lines.append("")
    return "\n".join(lines)


def publish_report(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = _state(ctx)
    inputs = state.get("inputs") or _inputs(ctx)
    warnings = [*(state.get("document_warnings") or []), *((state.get("rag") or {}).get("warnings") or []), *(state.get("web_warnings") or [])]
    final = build_final_artifact(inputs, state.get("evidence") or {}, state.get("recommendation") or {}, state.get("rag") or {}, state.get("sources") or [], warnings, state.get("documents") or [], state.get("actor_findings") or {}, ctx["run_id"], intake_plan=state.get("intake_plan") or {}, request=state.get("request") or {})
    final["candidate_comparisons"] = state.get("candidate_comparisons") or []
    final["preferred_candidate"] = (state.get("recommendation") or {}).get("preferred_candidate")
    final["source_refs"] = list(
        dict.fromkeys(
            [
                *(final.get("source_refs") or []),
                *(
                    url
                    for candidate in final["candidate_comparisons"]
                    for url in candidate.get("source_urls") or []
                    if url
                ),
            ]
        )
    )
    final["procurement_summary"] = build_procurement_summary(
        inputs, final["candidate_comparisons"], final["preferred_candidate"]
    )
    settings = analysis_settings(ctx["config"])
    candidate_packet, metrics = candidate_analysis_packet(
        final["candidate_comparisons"], max_candidates=settings["max_candidates"]
    )
    decision_analysis = state.get("decision_analysis") or {}
    risk_interpretation = state.get("risk_interpretation") or {}
    analysis_interpretation = state.get("analysis_interpretation") or {}
    payload = {
        "purchase": {
            "purchase_type": inputs.get("purchase_type"),
            "item_description": inputs.get("item_description"),
            "budget": inputs.get("budget"),
            "priorities": inputs.get("priorities") or [],
        },
        "authoritative_recommendation": {
            "label": final.get("recommended_action"),
            "confidence": final.get("confidence"),
            "preferred_candidate": final.get("preferred_candidate"),
            "rationale": final.get("recommendation_rationale"),
        },
        "procurement_summary": final["procurement_summary"],
        "candidate_results": candidate_packet,
        "authoritative_metrics": metrics,
        "analysis_interpretation": analysis_interpretation,
        "risk_interpretation": risk_interpretation,
        "decision_analysis": decision_analysis,
        "deterministic_risk_flags": final.get("risk_flags") or [],
        "deterministic_evidence_gaps": final.get("evidence_gaps") or [],
        "allowed_source_refs": sorted(known_source_refs(state))[: settings["max_list_items"]],
        "authority": {
            "rendering_is_deterministic": True,
            "numbers_hard_gates_ranking_and_recommendation_immutable": True,
            "return_structured_narrative_not_markdown": True,
        },
    }
    fallback = {
        "executive_summary": final["executive_summary"],
        "decision_rationale": final.get("recommendation_rationale") or "The deterministic recommendation requires human review.",
        "financial_interpretation": analysis_interpretation.get("summary") or "Deterministic lifecycle tables are authoritative; replace planning assumptions with approved business inputs before commitment.",
        "risk_interpretation": (
            f"The deterministic risk review has an {risk_interpretation.get('overall_posture')} posture and requires the listed verification before commitment."
            if risk_interpretation.get("overall_posture")
            else "The deterministic risk flags and evidence gaps require review before commitment."
        ),
        "alternative_tradeoffs": [
            {
                "candidate_id": item.get("candidate_id"),
                "interpretation": item.get("explanation"),
            }
            for item in decision_analysis.get("why_not_alternatives") or []
            if isinstance(item, dict) and item.get("candidate_id")
        ],
        "negotiation_points": list(risk_interpretation.get("negotiation_points") or []),
        "approval_conditions": list(decision_analysis.get("approval_conditions") or final.get("evidence_gaps") or []),
        "source_refs": [],
        **analysis_validation_context(state, payload),
    }
    report_narrative = generate_structured_analysis(
        state=state,
        config=ctx["config"],
        agent_id="purchase_report_writer",
        prompt_name="purchase-report-narrative-task.md",
        payload={
            **payload,
            "output_contract": {
                "executive_summary": "string",
                "decision_rationale": "string",
                "financial_interpretation": "string",
                "risk_interpretation": "string",
                "alternative_tradeoffs": "list of candidate_id and interpretation",
                "negotiation_points": "list of strings",
                "approval_conditions": "list of strings",
                "source_refs": "list drawn from allowed_source_refs",
            },
        },
        fallback=fallback,
        validator=validate_report_narrative,
        llm_client=llm_client,
    )
    final.update(
        {
            "executive_summary": report_narrative.get("executive_summary") or final["executive_summary"],
            "analysis_interpretation": analysis_interpretation,
            "risk_interpretation": risk_interpretation,
            "decision_analysis": decision_analysis,
            "report_narrative": report_narrative,
            "llm_generation": state.get("llm_generation") or {},
        }
    )
    final["warnings"] = [*warnings, *(state.get("llm_warnings") or [])]
    narrative_refs = [
        ref
        for section in (
            analysis_interpretation,
            risk_interpretation,
            decision_analysis,
            report_narrative,
        )
        for ref in section.get("source_refs") or []
        if isinstance(section, dict) and ref
    ]
    final["source_refs"] = list(dict.fromkeys([*(final.get("source_refs") or []), *narrative_refs]))
    run_status = (
        "completed_with_fallback"
        if (state.get("llm_generation") or {}).get("status") == "completed_with_fallback"
        else "completed"
    )
    result = {
        "identity": {"blueprint_id": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "run_id": ctx["run_id"]},
        "blueprint": BLUEPRINT_ID, "name": BLUEPRINT_NAME, "category": CATEGORY,
        "run": {"run_id": ctx["run_id"], "status": run_status}, "inputs": inputs,
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
    "build_procurement_summary",
    "publish_report",
    "render_markdown",
    "resolve_output_folder",
    "write_user_outputs",
]
