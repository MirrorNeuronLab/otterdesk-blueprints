"""Cross-lane evidence reconciliation and review audit."""

from .common import *
from .knowledge import load_prompt
from .review_services import actor_review, review_artifact

def step_advisor_evidence_reconciler(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    warnings = []
    for key in (
        "financial_document_reader",
        "bank_statement_extractor",
        "cash_flow_normalizer",
        "cash_flow_llm_analyst",
        "tax_document_router",
        "tax_form_ocr_capturer",
        "tax_workpaper_preparer",
        "tax_llm_reviewer",
        "portfolio_context_loader",
        "portfolio_market_data_loader",
        "portfolio_risk_engine",
        "portfolio_llm_reviewer",
        "public_finance_researcher",
    ):
        value = workflow.get(key) or {}
        warnings.extend(value.get("warnings") or [])
        warnings.extend(value.get("risk_flags") or [])
        warnings.extend(value.get("evidence_gaps") or [])
        warnings.extend(value.get("screening_threshold_flags") or [])
    profile_status = workflow.get("portfolio_context_loader", {}).get("customer_profile_status") or {}
    if profile_status.get("missing_fields"):
        warnings.append("customer_investment_profile_incomplete")
    evidence = [
        {
            "domain": "bank_statement",
            "summary": f"{workflow['bank_statement_extractor']['statement_count']} bank statement(s) extracted.",
            "source_refs": [item["source_ref"] for item in workflow["bank_statement_extractor"].get("statements", [])],
        },
        {
            "domain": "cash_flow",
            "summary": workflow["cash_flow_normalizer"].get("summary"),
            "source_refs": workflow["financial_document_reader"].get("source_refs", []),
        },
        {
            "domain": "cash_flow_llm_review",
            "summary": workflow["cash_flow_llm_analyst"].get("summary"),
            "source_refs": workflow["cash_flow_llm_analyst"].get("source_refs", []),
        },
        {
            "domain": "tax",
            "summary": f"{workflow['tax_document_router']['tax_document_count']} tax document(s) routed.",
            "source_refs": [
                item["source_ref"]
                for docs in workflow["tax_document_router"].get("groups", {}).values()
                for item in docs
            ],
        },
        {
            "domain": "tax_form_ocr_capture",
            "summary": f"{workflow['tax_form_ocr_capturer']['tax_form_count']} tax form image/answer packet(s) captured for review.",
            "source_refs": [
                form["source_ref"]
                for form in workflow["tax_form_ocr_capturer"].get("forms", [])
            ],
        },
        {
            "domain": "tax_llm_review",
            "summary": workflow["tax_llm_reviewer"].get("summary"),
            "source_refs": workflow["tax_llm_reviewer"].get("source_refs", []),
        },
        {
            "domain": "portfolio",
            "summary": f"{workflow['portfolio_context_loader']['holding_count']} holding(s) reviewed.",
            "source_refs": workflow["portfolio_market_data_loader"].get("source_refs", []),
        },
        {
            "domain": "portfolio_llm_review",
            "summary": workflow["portfolio_llm_reviewer"].get("summary"),
            "source_refs": workflow["portfolio_llm_reviewer"].get("source_refs", []),
        },
    ]
    return {
        "evidence": evidence,
        "warnings": sorted(set(warnings)),
        "contradictions": [],
        "missing_evidence": [
            warning for warning in warnings
            if warning.startswith("no_") or "missing" in warning or "incomplete" in warning or "not_extracted" in warning
        ],
    }

def step_advisor_review_auditor(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    reconciler = workflow["advisor_evidence_reconciler"]
    blocked_actions = (ctx["config"].get("human_control") or {}).get("blocked_actions") or []
    issues = []
    if reconciler.get("missing_evidence"):
        issues.append("missing_evidence_requires_review")
    if workflow["tax_workpaper_preparer"].get("manager_review", {}).get("blockers"):
        issues.append("tax_manager_review_blockers_present")
    if workflow["tax_form_ocr_capturer"].get("review_required_sources"):
        issues.append("tax_form_ocr_capture_review_required")
    if workflow["tax_form_ocr_capturer"].get("incomplete_sources"):
        issues.append("tax_substantive_fields_missing")
    if workflow["portfolio_risk_engine"].get("policy_violations"):
        issues.append("portfolio_policy_violations_present")
    if (workflow["portfolio_context_loader"].get("customer_profile_status") or {}).get("missing_fields"):
        issues.append("portfolio_suitability_not_assessable")
    llm_reviews = {
        "cash_flow": workflow["cash_flow_llm_analyst"],
        "tax": workflow["tax_llm_reviewer"],
        "portfolio": workflow["portfolio_llm_reviewer"],
    }
    if any(review.get("evidence_gaps") for review in llm_reviews.values()):
        issues.append("llm_review_evidence_gaps_present")
    if any(review.get("risk_flags") for review in llm_reviews.values()):
        issues.append("llm_review_risk_flags_present")
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "advisor_review_auditor",
        "Advisor packet audited for evidence, math, and blocked action boundaries.",
        {
            "issues": issues,
            "blocked_actions": blocked_actions,
            "llm_reviews": llm_reviews,
            "reconciled_evidence": reconciler.get("evidence", []),
            "missing_evidence": reconciler.get("missing_evidence", []),
            "review_constraints": [
                "Confirm LLM reviews did not alter deterministic math.",
                "Confirm blocked actions remain blocked.",
                "Only add human-review blockers and caveats.",
            ],
        },
        prompt_details=load_prompt("advisor-review-auditor.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    return {
        "issues": issues,
        "blocked_actions_confirmed": blocked_actions,
        "review_required": True,
        "actor_finding": finding,
        "quality_score": max(0.35, 0.9 - 0.08 * len(issues)),
        "warnings": ["human_review_required_before_downstream_action"],
    }

__all__ = ["step_advisor_evidence_reconciler", "step_advisor_review_auditor"]
