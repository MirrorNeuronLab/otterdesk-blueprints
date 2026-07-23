"""Candidate research, cost modeling, risk review, and recommendation audit."""

from __future__ import annotations

import json
from typing import Any

from mn_blueprint_support import llm_usage, resolve_actor_specs, run_actor_reviews

from .common import load_prompt, purchase_llm
from .research import ask_llm_for_recommendation, deterministic_evidence, deterministic_recommendation, research_public_sources
from .state import _inputs, _save, _state

def research_market(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    llm_config = ctx["config"].get("llm") if isinstance(ctx["config"].get("llm"), dict) else {}
    quick = str(llm_config.get("mode") or "live").lower() in {"fake", "mock"} or bool((ctx["config"].get("execution") or {}).get("quick_test"))
    sources, web_warnings = research_public_sources(state.get("research_queries") or [], ctx["config"], quick_test=quick)
    documents = state.get("documents") or []
    evidence = deterministic_evidence(inputs, documents, sources)
    state.update({"inputs": inputs, "sources": sources, "web_warnings": web_warnings, "evidence": evidence})
    _save(ctx, state)
    return {"source_count": len(sources), "query_count": len(state.get("research_queries") or [])}


def _candidate_records(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for document in documents:
        if str(document.get("suffix") or "").lower() != ".json":
            continue
        try:
            parsed = json.loads(str(document.get("text") or "{}"))
        except (TypeError, ValueError):
            continue
        values = parsed.get("candidates") if isinstance(parsed, dict) else None
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                candidate = dict(value)
                candidate.setdefault("source_ref", document.get("source_ref"))
                candidates.append(candidate)
    return candidates


def _money(value: Any) -> float | None:
    try:
        return round(float(value), 2) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def build_candidate_comparisons(
    inputs: dict[str, Any], documents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates = _candidate_records(documents)
    comparisons: list[dict[str, Any]] = []
    constraints = inputs.get("constraints") or {}
    for index, candidate in enumerate(candidates, start=1):
        asking = _money(candidate.get("asking_price"))
        closing = _money(candidate.get("closing_cost_estimate"))
        inspection = _money(candidate.get("inspection_reserve"))
        tax = _money(candidate.get("annual_property_tax"))
        insurance = _money(candidate.get("annual_insurance_estimate"))
        hoa = _money(candidate.get("hoa_monthly")) or 0.0
        known_upfront = round(sum(value or 0.0 for value in (asking, closing, inspection)), 2)
        known_annual = round(sum(value or 0.0 for value in (tax, insurance)) + hoa * 12, 2)
        hard_checks = {
            "property_type": not constraints.get("property_type") or str(candidate.get("property_type") or "").lower() == str(constraints.get("property_type") or "").lower(),
            "min_bedrooms": not constraints.get("min_bedrooms") or int(candidate.get("bedrooms") or 0) >= int(constraints.get("min_bedrooms") or 0),
            "zip_code": not constraints.get("zip_code") or str(candidate.get("zip_code") or "") == str(constraints.get("zip_code") or ""),
            "budget": inputs.get("budget") in (None, "") or (asking is not None and asking <= float(inputs["budget"])),
        }
        comparisons.append(
            {
                "candidate_id": str(candidate.get("candidate_id") or f"candidate_{index}"),
                "label": str(candidate.get("address") or candidate.get("name") or f"Candidate {index}"),
                "source_ref": candidate.get("source_ref"),
                "observed_at": candidate.get("observed_at"),
                "asking_price": asking,
                "known_upfront_cost": known_upfront,
                "known_annual_carry": known_annual,
                "known_five_year_cost_before_financing_utilities_and_resale": round(known_upfront + known_annual * 5, 2),
                "hard_constraint_checks": hard_checks,
                "hard_constraints_passed": all(hard_checks.values()),
                "condition": candidate.get("condition"),
                "disclosures": list(candidate.get("disclosures") or []),
                "unknown_costs": ["financing interest", "utilities", "maintenance beyond disclosed reserve", "transaction-specific legal and title costs", "resale proceeds"],
            }
        )
    comparisons.sort(
        key=lambda item: (
            not item["hard_constraints_passed"],
            item["known_five_year_cost_before_financing_utilities_and_resale"],
            item["candidate_id"],
        )
    )
    return comparisons


def analyze_total_cost(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    comparisons = build_candidate_comparisons(inputs, state.get("documents") or [])
    state["candidate_comparisons"] = comparisons
    _save(ctx, state)
    return {"candidate_count": len(comparisons), "constraint_match_count": sum(1 for item in comparisons if item["hard_constraints_passed"])}


def build_purchase_risk_review(
    comparisons: list[dict[str, Any]],
) -> dict[str, list[str]]:
    risk_flags: list[str] = []
    if not comparisons:
        risk_flags.append("No structured candidate records were available for comparison.")
    if comparisons and not any(item.get("hard_constraints_passed") for item in comparisons):
        risk_flags.append("No candidate satisfies every declared hard constraint.")
    for item in comparisons:
        if item.get("disclosures"):
            risk_flags.append(f"{item['candidate_id']}: disclosed condition items require qualified inspection and cost validation.")
        if not item.get("observed_at"):
            risk_flags.append(f"{item['candidate_id']}: listing observation date is missing.")
    evidence_gaps = [
        "Verify that the listing is active and the asking price has not changed.",
        "Obtain an independent inspection and specialist quotes for disclosed defects.",
        "Confirm taxes, insurability, title, zoning, utilities, and any association obligations.",
        "Model financing, cash-to-close, maintenance, and downside resale scenarios using customer-specific terms.",
    ]
    return {
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "evidence_gaps": evidence_gaps,
    }


def review_purchase_risks(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    review = build_purchase_risk_review(state.get("candidate_comparisons") or [])
    state.update(review)
    _save(ctx, state)
    return {"risk_count": len(review["risk_flags"]), "evidence_gap_count": len(review["evidence_gaps"])}


def audit_recommendation(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    sources = state.get("sources") or []
    evidence = state.get("evidence") or deterministic_evidence(inputs, state.get("documents") or [], sources)
    deterministic = deterministic_recommendation(evidence, sources)
    comparisons = state.get("candidate_comparisons") or []
    eligible = [item for item in comparisons if item.get("hard_constraints_passed")]
    if eligible:
        deterministic = {
            "label": "consider",
            "confidence": "low" if not any(item.get("status") == "observed" for item in sources) else "medium",
            "rationale": "At least one locally supplied candidate satisfies the declared hard constraints, but material property, condition, financing, and listing-freshness checks remain open.",
        }
    llm = purchase_llm(ctx["config"])
    recommendation = ask_llm_for_recommendation(llm, inputs, evidence, state.get("rag") or {}, deterministic)
    recommendation.update(
        {
            "preferred_candidate": eligible[0].get("candidate_id") if eligible else None,
            "risk_flags": state.get("risk_flags") or [],
            "evidence_gaps": state.get("evidence_gaps") or [],
        }
    )
    actor_findings = run_actor_reviews(
        config=ctx["config"], llm=llm,
        actor_ids=[agent_id for agent_id in ("purchase_recommendation_auditor",) if agent_id in resolve_actor_specs(ctx["config"])], state={},
        task=load_prompt("purchase-review-task.md"),
        context={"inputs": inputs, "intake_plan": state.get("intake_plan") or {}, "evidence": evidence, "candidate_comparisons": comparisons, "recommendation": recommendation, "rag": state.get("rag") or {}, "sources": sources},
    )
    state.update({"inputs": inputs, "evidence": evidence, "recommendation": recommendation, "actor_findings": actor_findings, "llm_usage": llm_usage(llm)})
    _save(ctx, state)
    return {"recommended_action": recommendation["label"], "preferred_candidate": recommendation.get("preferred_candidate")}
