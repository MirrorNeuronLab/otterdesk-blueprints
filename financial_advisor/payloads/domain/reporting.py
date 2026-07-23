"""Customer readiness, action queue, and financial packet publication."""

from .common import *
from .knowledge import financial_knowledge_reference, load_prompt
from .review_services import actor_review, effective_llm_usage, review_artifact
from .source_ingestion import money

def build_customer_action_queue(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    cash = workflow.get("cash_flow_normalizer") or {}
    tax_capture = workflow.get("tax_form_ocr_capturer") or {}
    portfolio = workflow.get("portfolio_risk_engine") or {}
    portfolio_context = workflow.get("portfolio_context_loader") or {}
    actions: list[dict[str, Any]] = []

    incomplete_tax_sources = list(tax_capture.get("incomplete_sources") or [])
    if incomplete_tax_sources:
        actions.append({
            "priority": "Critical",
            "customer_action": "Provide or verify substantive fields for the identified Schedule E forms.",
            "why_it_matters": "The draft tax income total may be incomplete because form amounts were not captured.",
            "owner": "Customer and qualified tax reviewer",
            "completion_condition": "All expected Schedule E income or loss fields are extracted and reconciled to the source images.",
            "source_refs": incomplete_tax_sources,
        })
    missing_tax_forms = list((workflow.get("tax_document_router") or {}).get("missing_recommended_forms") or [])
    if missing_tax_forms:
        actions.append({
            "priority": "Critical",
            "customer_action": f"Provide or verify the expected tax documents: {', '.join(missing_tax_forms)}.",
            "why_it_matters": "The tax packet cannot establish document completeness when expected source forms are absent.",
            "owner": "Customer and qualified tax reviewer",
            "completion_condition": "Expected forms are present, classified, and reconciled to the tax-year profile.",
            "source_refs": ["workflow_input:tax_documents"],
        })

    if portfolio.get("holdings") and (portfolio.get("warnings") or "fixture" in str((portfolio.get("risk_methodology") or {}).get("price_data"))):
        actions.append({
            "priority": "High",
            "customer_action": "Confirm holdings, cash, and current prices against a current brokerage statement.",
            "why_it_matters": "The portfolio values currently use test or fixture prices and may not represent current balances.",
            "owner": "Customer or advisor reviewer",
            "completion_condition": "Holdings and as-of prices agree with a current brokerage statement.",
            "source_refs": list((portfolio_context.get("portfolio_source_refs") or [])) + list((workflow.get("portfolio_market_data_loader") or {}).get("source_refs") or []),
        })

    missing_profile = list((portfolio_context.get("customer_profile_status") or {}).get("missing_fields") or [])
    if missing_profile:
        actions.append({
            "priority": "High",
            "customer_action": "Complete the goals and risk questionnaire before considering an allocation change.",
            "why_it_matters": "Allocation appropriateness cannot be assessed without purpose, time horizon, liquidity needs, risk tolerance, and tax context.",
            "owner": "Customer with advisor review",
            "completion_condition": "Investment objective, horizon, liquidity, risk tolerance, tax objective, and other-account coverage are recorded.",
            "source_refs": ["workflow_input:customer_profile"],
        })

    if cash.get("pending_classification_total"):
        actions.append({
            "priority": "Medium",
            "customer_action": f"Identify the {money(cash.get('pending_classification_total'))} card payment or transfer.",
            "why_it_matters": "It may be a transfer or credit-card balance payment rather than new household spending.",
            "owner": "Customer",
            "completion_condition": "The transaction type is confirmed and the cash-flow summary is updated without double counting.",
            "source_refs": [
                f"{item.get('source_ref')}#line-{item.get('line_no')}"
                for statement in (workflow.get("bank_statement_extractor") or {}).get("statements", [])
                for item in statement.get("transactions", [])
                if item.get("classification_status") == "pending_customer_confirmation"
            ],
        })

    fee_review = cash.get("fee_review") or {}
    if fee_review.get("fee_total"):
        actions.append({
            "priority": "Low",
            "customer_action": f"Review the {money(fee_review.get('fee_total'))} service fee and whether it recurs.",
            "why_it_matters": f"If it recurs monthly, the annual cost would be approximately {money(fee_review.get('annual_cost_if_monthly'))}; waiver terms were not supplied.",
            "owner": "Customer",
            "completion_condition": "Fee recurrence and any applicable waiver condition are confirmed from account terms.",
            "source_refs": [
                f"{item.get('source_ref')}#line-{item.get('line_no')}"
                for statement in (workflow.get("bank_statement_extractor") or {}).get("statements", [])
                for item in statement.get("transactions", [])
                if item.get("direction") == "fee"
            ],
        })

    rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(actions, key=lambda item: rank.get(item.get("priority"), 99))

def customer_readiness(final_artifact: dict[str, Any]) -> dict[str, Any]:
    cash = final_artifact.get("household_finance_summary") or {}
    tax_capture = final_artifact.get("tax_form_ocr_capture") or {}
    portfolio = final_artifact.get("portfolio_risk_review") or {}
    cash_status = "moderate" if cash.get("statement_periods") and cash.get("statement_count") else "low"
    if cash.get("pending_classification_total"):
        cash_label = "Moderate — arithmetic reconciles, but one transaction still needs classification and the account history is limited."
    else:
        cash_label = "Moderate — arithmetic reconciles for the supplied statement, but broader account coverage is not established."
    tax_status = "low" if tax_capture.get("incomplete_sources") else "moderate"
    tax_label = (
        "Low — tax-form images were identified, but substantive Schedule E fields were not captured."
        if tax_status == "low"
        else "Moderate — supplied tax fields were captured, but human reconciliation is still required."
    )
    suitability_complete = portfolio.get("suitability_assessment", {}).get("status") == "complete"
    portfolio_status = "low" if portfolio.get("warnings") or not suitability_complete else "moderate"
    if not suitability_complete:
        portfolio_label = "Low — customer objectives are incomplete, so suitability is not assessable."
    elif portfolio.get("warnings"):
        portfolio_label = "Low — customer objectives were supplied, but holdings use fixture prices and must be refreshed before advisor review."
    else:
        portfolio_label = "Moderate — holdings and customer profile were supplied, but this remains a review-only risk estimate."
    return {
        "cash_flow": {"status": cash_status, "label": cash_label},
        "tax": {"status": tax_status, "label": tax_label},
        "portfolio": {"status": portfolio_status, "label": portfolio_label},
    }

def build_customer_report(final_artifact: dict[str, Any]) -> dict[str, Any]:
    cash = final_artifact.get("household_finance_summary") or {}
    tax = final_artifact.get("tax_review_packet") or {}
    tax_capture = final_artifact.get("tax_form_ocr_capture") or {}
    portfolio = final_artifact.get("portfolio_risk_review") or {}
    readiness = customer_readiness(final_artifact)
    return {
        "title": "Your preliminary financial snapshot",
        "status": "review_required",
        "summary": "This snapshot organizes the supplied documents, but it is not ready to support filing, trading, or other financial action.",
        "data_coverage": {
            "bank_statements": (final_artifact.get("bank_statement_extraction") or {}).get("statement_count", 0),
            "tax_form_images": tax_capture.get("tax_form_count", 0),
            "portfolio_holdings": len(portfolio.get("holdings") or []),
            "account_coverage": cash.get("account_coverage", "unknown"),
            "statement_periods": cash.get("statement_periods") or [],
        },
        "cash_flow": {
            "status": readiness["cash_flow"],
            "deposits": cash.get("income_total"),
            "confirmed_spending_and_fees": cash.get("confirmed_spending_and_fees_total"),
            "transfer_or_card_payment_pending": cash.get("pending_classification_total"),
            "preliminary_net_cash_flow": cash.get("preliminary_net_cash_flow"),
            "closing_balance": cash.get("closing_balance"),
            "fee_review": cash.get("fee_review"),
        },
        "tax": {
            "status": readiness["tax"],
            "draft_income_total": tax.get("workpapers", {}).get("draft_income_total"),
            "included_source_refs": tax.get("workpapers", {}).get("included_source_refs", []),
            "unextracted_form_sources": tax_capture.get("incomplete_sources", []),
            "message": "The draft income total excludes any amounts on forms whose substantive fields were not extracted.",
        },
        "portfolio": {
            "status": readiness["portfolio"],
            "total_value": portfolio.get("total_value"),
            "cash_weight_pct": portfolio.get("cash_weight_pct"),
            "largest_position": portfolio.get("largest_position"),
            "risk_methodology": {
                "estimated_adverse_day_loss": portfolio.get("risk_methodology", {}).get("estimated_adverse_day_loss"),
                "estimated_cvar_loss": portfolio.get("risk_methodology", {}).get("estimated_cvar_loss"),
                "holding_period": portfolio.get("risk_methodology", {}).get("holding_period"),
                "confidence_level": portfolio.get("risk_methodology", {}).get("confidence_level"),
            },
            "suitability": portfolio.get("suitability_assessment"),
        },
        "top_actions": final_artifact.get("action_queue", []),
        "review_boundary": "This is a review-only snapshot. A human must approve any filing, trade, money movement, bill payment, external sharing, or financial decision.",
        "source_refs": final_artifact.get("source_refs", []),
    }

def build_final_artifact(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    cash = workflow["cash_flow_normalizer"]
    cash_llm = workflow["cash_flow_llm_analyst"]
    tax = workflow["tax_workpaper_preparer"]
    tax_capture = workflow["tax_form_ocr_capturer"]
    tax_llm = workflow["tax_llm_reviewer"]
    portfolio = workflow["portfolio_risk_engine"]
    portfolio_llm = workflow["portfolio_llm_reviewer"]
    reconciler = workflow["advisor_evidence_reconciler"]
    auditor = workflow["advisor_review_auditor"]
    confidence = round(min(0.86, max(0.45, auditor.get("quality_score", 0.75))), 2)
    action_queue = build_customer_action_queue(workflow)
    cash_period = next(
        (item.get("label") for item in cash.get("statement_periods", []) if item.get("label")),
        "unknown statement period",
    )
    summary_parts = [
        f"Bank/cash-flow review for {cash_period} detected preliminary net cash flow of {money(cash.get('net_cash_flow'))}.",
        f"Draft tax workpapers show included-source income of {money(tax.get('workpapers', {}).get('draft_income_total'))}.",
        f"Tax form intake identified {tax_capture.get('tax_form_count', 0)} form image/answer packet(s), with {len(tax_capture.get('incomplete_sources') or [])} source(s) still lacking substantive fields.",
        f"Portfolio risk review estimated total value at {money(portfolio.get('total_value'))} with largest position weight {portfolio.get('largest_position_weight_pct')}%.",
    ]
    warnings = sorted(set(reconciler.get("warnings") or []) | set(auditor.get("warnings") or []))
    artifact = {
        "type": OUTPUT_TYPE,
        "blueprint_id": BLUEPRINT_ID,
        "run_id": ctx["run_id"],
        "generated_at": utc_now_iso(),
        "executive_summary": " ".join(summary_parts),
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": reconciler.get("evidence") or [],
        "next_steps": [item["customer_action"] for item in action_queue],
        "action_queue": action_queue,
        "customer_readiness": customer_readiness({
            "household_finance_summary": cash,
            "bank_statement_extraction": workflow["bank_statement_extractor"],
            "tax_review_packet": tax,
            "tax_form_ocr_capture": tax_capture,
            "portfolio_risk_review": portfolio,
        }),
        "source_refs": sorted(
            set(workflow["financial_document_reader"].get("source_refs", []))
            | set(workflow["portfolio_market_data_loader"].get("source_refs", []))
            | set(workflow["public_finance_researcher"].get("source_refs", []))
            | set(cash_llm.get("source_refs") or [])
            | set(tax_llm.get("source_refs") or [])
            | set(portfolio_llm.get("source_refs") or [])
        ),
        "research_summary": {
            "topics": workflow["public_finance_researcher"].get("topics", []),
            "warnings": workflow["public_finance_researcher"].get("warnings", []),
        },
        "research_sources": workflow["public_finance_researcher"].get("sources", []),
        "research_warnings": warnings,
        "knowledge_grounding": financial_knowledge_reference(ctx.get("active_knowledge")),
        "document_ingestion": {
            "document_count": workflow["financial_document_reader"].get("document_count", 0),
            "kind_counts": workflow["financial_document_reader"].get("kind_counts", {}),
            "ocr": workflow["financial_document_reader"].get("ocr", {}),
            "ocr_required_count": workflow["financial_document_reader"].get("ocr_required_count", 0),
            "ocr_required_sources": workflow["financial_document_reader"].get("ocr_required_sources", []),
        },
        "bank_statement_extraction": workflow["bank_statement_extractor"],
        "household_finance_summary": cash,
        "llm_analysis": {
            "cash_flow": cash_llm,
            "tax": tax_llm,
            "portfolio": portfolio_llm,
            "review_only": True,
        },
        "tax_review_packet": tax,
        "tax_form_ocr_capture": tax_capture,
        "portfolio_risk_review": portfolio,
        "auditor_review": auditor,
        "model_profiles_used": ctx["state"].get("model_profiles_used", {}),
        "llm_usage": effective_llm_usage(ctx),
        "review_only": True,
        "blocked_actions": (ctx["config"].get("human_control") or {}).get("blocked_actions") or [],
    }
    artifact["customer_report"] = build_customer_report(artifact)
    artifact["review_status"] = "review_required"
    return artifact

def markdown_review_section(title: str, review: dict[str, Any]) -> list[str]:
    findings = [str(item) for item in listify(review.get("key_findings"))] or ["No additional LLM findings returned."]
    questions = [str(item) for item in listify(review.get("review_questions"))] or ["No additional review questions returned."]
    gaps = [str(item) for item in listify(review.get("evidence_gaps"))] or ["none"]
    risks = [str(item) for item in listify(review.get("risk_flags"))] or ["none"]
    return [
        f"## {title}",
        "",
        str(review.get("summary") or "LLM review completed."),
        "",
        f"- Key findings: {'; '.join(findings)}",
        f"- Review questions: {'; '.join(questions)}",
        f"- Evidence gaps: {'; '.join(gaps)}",
        f"- Risk flags: {'; '.join(risks)}",
        f"- Confidence: {review.get('confidence')}",
        "",
    ]

def markdown_report(final_artifact: dict[str, Any]) -> str:
    customer = final_artifact.get("customer_report") or build_customer_report(final_artifact)
    cash = customer.get("cash_flow") or {}
    tax = customer.get("tax") or {}
    portfolio = customer.get("portfolio") or {}
    coverage = customer.get("data_coverage") or {}
    readiness = final_artifact.get("customer_readiness") or {}
    actions = customer.get("top_actions") or []
    readiness_cash = readiness.get("cash_flow", {}).get("label") or "Arithmetic reflects the supplied statement only."
    lines = [
        "# Your Preliminary Financial Snapshot",
        "",
        customer.get("summary") or "This snapshot is review-only.",
        "",
        "## What We Reviewed",
        "",
        f"- Bank statements: {coverage.get('bank_statements', 0)}",
        f"- Statement period: {', '.join(item.get('label') for item in coverage.get('statement_periods', []) if item.get('label')) or 'not provided'}",
        f"- Account coverage: {coverage.get('account_coverage', 'unknown')}",
        f"- Tax-form images: {coverage.get('tax_form_images', 0)}",
        f"- Portfolio holdings: {coverage.get('portfolio_holdings', 0)}",
        "",
        "## Cash Flow — Needs Transaction Confirmation",
        "",
    ]
    lines.extend([
        readiness_cash,
        "",
        f"- Deposits: {money(cash.get('deposits'))}",
        f"- Confirmed spending and fees: {money(cash.get('confirmed_spending_and_fees'))}",
        f"- Transfer or card payment pending classification: {money(cash.get('transfer_or_card_payment_pending'))}",
        f"- Preliminary positive cash flow: {money(cash.get('preliminary_net_cash_flow'))}",
        f"- Closing balance: {money(cash.get('closing_balance'))}",
        "",
        "A card payment may be a transfer or a credit-card balance payment. Confirm its type before treating it as household spending.",
    ])
    fee_review = cash.get("fee_review") or {}
    if fee_review.get("fee_total"):
        lines.extend([
            "",
            f"A {money(fee_review.get('fee_total'))} service fee was detected. If it recurs monthly, the annual cost would be approximately {money(fee_review.get('annual_cost_if_monthly'))}. Waiver terms were not supplied.",
        ])
    lines.extend([
        "",
        "## Tax Preparation — Not Ready",
        "",
    ])
    readiness_tax = readiness.get("tax", {}).get("label") or "Tax evidence remains review-required."
    lines.extend([
        readiness_tax,
        "",
        f"- Draft income from extracted W-2, 1099-INT, and 1099-R fields: {money(tax.get('draft_income_total'))}",
        f"- Forms with no substantive fields extracted: {', '.join(tax.get('unextracted_form_sources') or ['none'])}",
        "",
        "The draft income total excludes any amounts on forms whose substantive fields were not extracted. Do not use it for filing or tax-liability decisions until those forms are extracted and reconciled.",
        "",
        "## Investments — Suitability Not Yet Assessable",
        "",
    ])
    readiness_portfolio = readiness.get("portfolio", {}).get("label") or "Portfolio context remains review-required."
    lines.extend([
        readiness_portfolio,
        "",
        f"- Supplied portfolio value: {money(portfolio.get('total_value'))}",
        f"- Cash allocation: {portfolio.get('cash_weight_pct')}%",
        f"- Largest position: {(portfolio.get('largest_position') or {}).get('symbol') or 'not provided'} at {(portfolio.get('largest_position') or {}).get('weight_pct', 'unknown')}%",
        "",
        "SPY is a diversified S&P 500 ETF, not a single company. A large allocation to one ETF can still create substantial dependence on U.S. large-cap equities.",
        f"The model's one-day adverse scenario is approximately {money((portfolio.get('risk_methodology') or {}).get('estimated_adverse_day_loss'))}; this is a review estimate based on supplied test prices, not a forecast or trade signal.",
        "",
        "No customer-specific allocation judgment is provided until purpose, time horizon, liquidity needs, risk tolerance, tax objectives, and other-account coverage are confirmed.",
        "",
        "## Priority Actions",
        "",
        *[
            f"- **{item.get('priority')}** — {item.get('customer_action')} Why: {item.get('why_it_matters')} Completion: {item.get('completion_condition')}"
            for item in actions
        ],
        "",
        "## Review Boundary",
        "",
        customer.get("review_boundary") or "Review-only; human approval is required before downstream financial action.",
        "",
        "Source references are retained in the audit packet for the customer or advisor to inspect.",
        "",
        "<!-- Audit-only review artifacts are stored separately: ## Document Ingestion and OCR; ## LLM Cash-Flow Review; ## LLM Tax Review; ## LLM Portfolio Review. -->",
    ])
    return "\n".join(lines) + "\n"

def step_financial_advice_reporter(ctx: dict[str, Any]) -> dict[str, Any]:
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "financial_advice_reporter",
        "Integrated financial advisor report written for human review.",
        {
            "workflow_keys": sorted(ctx["state"]["workflow"]),
            "llm_reviews": {
                "cash_flow": ctx["state"]["workflow"].get("cash_flow_llm_analyst"),
                "tax": ctx["state"]["workflow"].get("tax_llm_reviewer"),
                "portfolio": ctx["state"]["workflow"].get("portfolio_llm_reviewer"),
            },
            "auditor_review": ctx["state"]["workflow"].get("advisor_review_auditor"),
            "review_constraints": [
                "Do not change deterministic extraction or calculation fields.",
                "Include LLM analysis as review notes only.",
                "Keep filing, trading, money movement, bill payment, and external sharing blocked until human approval.",
            ],
        },
        prompt_details=load_prompt("financial-advice-reporter.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    ctx["state"].setdefault("actor_findings", {})["financial_advice_reporter"] = finding
    final_artifact = build_final_artifact(ctx)
    output_folder = ctx["output_folder"]
    artifacts = {
        "bank_statement_extraction.json": final_artifact["bank_statement_extraction"],
        "household_finance_summary.json": final_artifact["household_finance_summary"],
        "cash_flow_llm_review.json": final_artifact["llm_analysis"]["cash_flow"],
        "tax_review_packet.json": final_artifact["tax_review_packet"],
        "tax_form_ocr_capture.json": final_artifact["tax_form_ocr_capture"],
        "tax_llm_review.json": final_artifact["llm_analysis"]["tax"],
        "portfolio_risk_review.json": final_artifact["portfolio_risk_review"],
        "portfolio_llm_review.json": final_artifact["llm_analysis"]["portfolio"],
        "customer_report.json": final_artifact["customer_report"],
        "action_ledger.json": {
            "review_only": True,
            "blocked_actions": final_artifact["blocked_actions"],
            "recommended_action": final_artifact["recommended_action"],
        },
        "artifact_quality.json": {
            "confidence": final_artifact["confidence"],
            "audit_confidence": final_artifact["confidence"],
            "customer_status": final_artifact["review_status"],
            "warnings": final_artifact["research_warnings"],
            "required_fields_present": all(final_artifact.get(key) for key in ("type", "executive_summary", "recommended_action", "evidence", "next_steps", "llm_analysis", "customer_report", "action_queue")),
            "customer_report_fields_present": all(final_artifact["customer_report"].get(key) for key in ("title", "status", "summary", "data_coverage", "top_actions", "review_boundary")),
        },
        "run_health.json": {
            "status": "completed",
            "warnings_count": len(final_artifact["research_warnings"]),
            "llm_provider": final_artifact["llm_usage"].get("provider"),
            "llm_model": final_artifact["llm_usage"].get("model"),
            "llm_calls": final_artifact["llm_usage"].get("calls"),
            "llm_usage": final_artifact["llm_usage"],
        },
    }
    written = []
    for name, value in artifacts.items():
        path = output_folder / name
        write_json(path, value)
        written.append(str(path))
    report_path = output_folder / "financial_advisor_report.md"
    write_text(report_path, markdown_report(final_artifact))
    written.append(str(report_path))
    return {
        "final_artifact": final_artifact,
        "output_files": written,
        "actor_finding": finding,
        "markdown_report": str(report_path),
    }

__all__ = ["step_financial_advice_reporter"]
