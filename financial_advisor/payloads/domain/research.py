"""Public financial-guidance source register."""

from .common import *
from .review_services import listify

def step_public_finance_researcher(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    cash_flow = workflow["cash_flow_normalizer"]
    cash_llm = workflow.get("cash_flow_llm_analyst", {})
    tax = workflow["tax_workpaper_preparer"]
    tax_llm = workflow.get("tax_llm_reviewer", {})
    portfolio = workflow["portfolio_risk_engine"]
    portfolio_llm = workflow.get("portfolio_llm_reviewer", {})
    topics = ["budget and cash-flow review", "bank account fee review"]
    if cash_llm.get("risk_flags") or cash_llm.get("review_questions"):
        topics.append("cash-flow evidence gaps and review questions")
    if tax.get("manager_review", {}).get("blockers"):
        topics.append("tax records and missing form review")
    if tax_llm.get("evidence_gaps"):
        topics.append("tax evidence gap review")
    if workflow["tax_form_ocr_capturer"].get("tax_form_count"):
        topics.append("tax form OCR field validation review")
    if portfolio.get("policy_violations"):
        topics.append("portfolio concentration and risk tolerance review")
    if portfolio_llm.get("evidence_gaps"):
        topics.append("portfolio market evidence verification")
    sources = [
        source for source in PUBLIC_GUIDANCE_SOURCES
        if any(token in source["topic"] for token in ("budget", "bank", "tax", "portfolio", "risk"))
    ]
    return {
        "topics": topics,
        "sources": sources,
        "source_refs": [source["url"] for source in sources],
        "warnings": [
            "public_research_uses_generic_topics_only",
            "source_summaries_are_for_review_context_not_personalized_action"
        ],
        "cash_flow_flags": cash_flow.get("risk_flags") or [],
        "llm_review_flags": sorted(
            {
                str(item)
                for review in (cash_llm, tax_llm, portfolio_llm)
                for item in listify(review.get("risk_flags")) + listify(review.get("evidence_gaps"))
                if str(item)
            }
        ),
    }

__all__ = ["step_public_finance_researcher"]
