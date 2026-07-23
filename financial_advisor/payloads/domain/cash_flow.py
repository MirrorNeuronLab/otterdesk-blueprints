"""Cash-flow normalization and source-grounded household review."""

from .common import *
from .review_services import review_artifact
from .source_ingestion import classify_cash_transaction, money

def step_cash_flow_normalizer(ctx: dict[str, Any]) -> dict[str, Any]:
    bank = ctx["state"]["workflow"]["bank_statement_extractor"]
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    income_docs = [doc for doc in docs if doc["kind"] in {"income_document", "w2", "1099_int", "1099_r"}]
    totals = bank.get("totals") or {}
    income = float(totals.get("deposits") or 0.0)
    expenses = float(totals.get("withdrawals") or 0.0) + float(totals.get("fees") or 0.0)
    pending_classification_total = float(bank.get("pending_classification_total") or 0.0)
    confirmed_spending_and_fees = max(0.0, expenses - pending_classification_total)
    warnings = []
    if income <= 0 and income_docs:
        warnings.append("income_documents_present_but_no_bank_deposits_detected")
    if totals.get("fees", 0) > 0:
        warnings.append("bank_fees_detected_for_review")
    if expenses > income and income > 0:
        warnings.append("expenses_exceed_detected_income")
    if pending_classification_total:
        warnings.append("card_payment_or_transfer_requires_customer_classification")
    return {
        "income_total": income,
        "expense_total": expenses,
        "fee_total": float(totals.get("fees") or 0.0),
        "net_cash_flow": income - expenses,
        "preliminary_net_cash_flow": income - expenses,
        "confirmed_spending_and_fees_total": round(confirmed_spending_and_fees, 2),
        "pending_classification_total": round(pending_classification_total, 2),
        "statement_count": bank.get("statement_count", 0),
        "statement_periods": bank.get("statement_periods", []),
        "account_names": bank.get("account_names", []),
        "account_coverage": bank.get("account_coverage", "unknown"),
        "fee_review": copy.deepcopy(bank.get("fee_review") or {}),
        "closing_balance": bank.get("closing_balance", 0.0),
        "income_document_count": len(income_docs),
        "risk_flags": warnings,
        "summary": f"Detected {money(income)} income-like deposits and {money(expenses)} expenses/fees.",
    }

def step_cash_flow_llm_analyst(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    cash_flow = workflow["cash_flow_normalizer"]
    bank = workflow["bank_statement_extractor"]
    docs = workflow["financial_document_reader"]
    source_refs = sorted(
        {
            str(item.get("source_ref"))
            for statement in bank.get("statements", [])
            for item in statement.get("transactions", [])
            if item.get("source_ref")
        }
        | {str(item) for item in docs.get("source_refs", []) if item}
    )
    risk_flags = list(cash_flow.get("risk_flags") or [])
    evidence_gaps = []
    if not bank.get("statement_count"):
        evidence_gaps.append("No bank statements were available for cash-flow validation.")
    if cash_flow.get("income_total", 0) <= 0:
        evidence_gaps.append("No income-like deposits were detected in statement evidence.")
    if cash_flow.get("income_document_count", 0) and cash_flow.get("income_total", 0) <= 0:
        evidence_gaps.append("Income documents exist but did not reconcile to detected deposits.")
    if not cash_flow.get("statement_periods"):
        evidence_gaps.append("Statement dates were not available, so the cash-flow period is unknown.")
    if cash_flow.get("account_coverage") != "one_statement_and_one_account":
        evidence_gaps.append("Account coverage is incomplete or spans more than one statement scope.")
    if cash_flow.get("pending_classification_total"):
        evidence_gaps.append("A card payment or transfer is included in withdrawals but not confirmed as household spending.")
    return review_artifact(
        ctx,
        step_id="cash_flow_llm_analyst",
        summary="Cash-flow LLM analyst reviewed deterministic cash-flow totals for gaps, recurring-risk signals, and human questions.",
        context={
            "cash_flow_normalizer": cash_flow,
            "bank_statement_extractor": {
                "statement_count": bank.get("statement_count"),
                "totals": bank.get("totals"),
                "opening_balance": bank.get("opening_balance"),
                "closing_balance": bank.get("closing_balance"),
                "net_cash_flow": bank.get("net_cash_flow"),
                "transaction_count": sum(len(statement.get("transactions", [])) for statement in bank.get("statements", [])),
            },
            "document_reader": {
                "document_count": docs.get("document_count"),
                "kind_counts": docs.get("kind_counts"),
                "warnings": docs.get("warnings"),
            },
            "review_constraints": [
                "Do not alter deterministic income, expense, fee, or net cash-flow totals.",
                "Only identify review gaps, risks, and human follow-up questions.",
            ],
        },
        source_refs=source_refs,
        key_findings=[
            f"Detected {money(cash_flow.get('income_total'))} income-like deposits and {money(cash_flow.get('expense_total'))} expenses/fees.",
            f"Net cash flow is {money(cash_flow.get('net_cash_flow'))} based on deterministic statement parsing.",
            f"{money(cash_flow.get('pending_classification_total'))} remains transfer or card-payment classification pending.",
        ],
        review_questions=[
            "Do statement totals match the source bank statement pages?",
            "Are any recurring withdrawals, fees, bills, or transfers missing from the parsed evidence?",
        ],
        evidence_gaps=evidence_gaps,
        risk_flags=risk_flags,
        next_steps=[
            "Compare parsed deposits, withdrawals, and fees against source statements.",
            "Confirm whether flagged cash-flow items require human budgeting or records review.",
        ],
    )

__all__ = ["step_cash_flow_llm_analyst", "step_cash_flow_normalizer"]
