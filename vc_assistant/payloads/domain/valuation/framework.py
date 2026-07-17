"""Shared deterministic scorer execution and VC audit adaptation."""

from __future__ import annotations

from typing import Any

from ..common import (
    METHOD_IDS,
    bounded_int,
    run_scorers,
    shared_audit_method_scores,
    utc_now_iso,
)
from .berkus import score_berkus
from .comparables import score_comparables
from .cost_to_duplicate import score_cost_to_duplicate
from .first_chicago import score_first_chicago
from .risk_factor import score_risk_factor_summation
from .scorecard import score_scorecard
from .venture_capital import score_venture_capital_method

def score_company_methods(facts: dict[str, Any], max_workers: int = 1) -> dict[str, Any]:
    scorers = [
        score_berkus,
        score_scorecard,
        score_risk_factor_summation,
        score_venture_capital_method,
        score_first_chicago,
        score_comparables,
        score_cost_to_duplicate,
    ]
    worker_count = bounded_int(max_workers, default=min(7, len(scorers)), maximum=len(scorers))
    results = run_scorers(scorers, facts, max_workers=worker_count)
    by_method = {result["method_id"]: result for result in results}
    return {method_id: by_method[method_id] for method_id in METHOD_IDS}

def audit_method_scores(methods: dict[str, dict[str, Any]], facts: dict[str, Any]) -> dict[str, Any]:
    contract = shared_audit_method_scores(methods, required_method_ids=METHOD_IDS)
    findings = [
        {"severity": "error", "method_id": method_id, "message": "Method score missing."}
        for method_id in contract["missing_methods"]
    ]
    for method_id in METHOD_IDS:
        method = methods.get(method_id)
        if not method:
            continue
        if method_id in contract["invalid_scored_methods"]:
            findings.append({"severity": "error", "method_id": method_id, "message": "Scored method has no numeric score."})
        if method["status"] == "insufficient_evidence" and method["score"] is not None:
            findings.append({"severity": "warning", "method_id": method_id, "message": "Insufficient-evidence method should not carry a numeric score."})
        for field in ("inputs_used", "formula_or_weighting", "assumptions", "source_refs", "evidence_refs", "evidence_summary", "missing_evidence", "warnings"):
            if field not in method:
                findings.append({"severity": "error", "method_id": method_id, "message": f"Missing {field}."})
        if method_id == "scorecard_bill_payne_method" and method["status"] == "scored" and method.get("details", {}).get("non_substantive_default_inputs"):
            findings.append({"severity": "warning", "method_id": method_id, "message": "Scorecard includes non-substantive default inputs; substantive evidence gates controlled scoring status."})
    unsupported = []
    if facts["financial_facts"]["largest_local_value"] and not facts["traction_facts"]["score"]:
        unsupported.append("Financial value found without traction terms; review whether value is relevant.")
    return {
        "company_name": facts["company_name"],
        "company_slug": facts["company_slug"],
        "status": "checked_with_warnings" if findings or unsupported else "checked",
        "findings": findings,
        "unsupported_assumption_warnings": unsupported,
        "checked_at": utc_now_iso(),
    }

METHOD_SCORER_FUNCTIONS = {
    "berkus_method": score_berkus,
    "scorecard_bill_payne_method": score_scorecard,
    "risk_factor_summation_method": score_risk_factor_summation,
    "venture_capital_method": score_venture_capital_method,
    "first_chicago_method": score_first_chicago,
    "comparables_market_multiple_method": score_comparables,
    "cost_to_duplicate_method": score_cost_to_duplicate,
}

