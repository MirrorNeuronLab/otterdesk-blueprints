"""Financial document inventory, extraction, and statement packet operations."""

from .common import *
from .source_ingestion import *

def step_financial_folder_watcher(ctx: dict[str, Any]) -> dict[str, Any]:
    files = iter_input_files(ctx["document_folder"])
    result = {
        "document_folder": str(ctx["document_folder"]),
        "output_folder": str(ctx["output_folder"]),
        "file_count": len(files),
        "files": [fingerprint_file(path) for path in files],
        "monitoring": ctx["payload"].get("monitoring") or {},
        "ready": True,
    }
    return result

def step_financial_document_reader(ctx: dict[str, Any]) -> dict[str, Any]:
    ocr_client, ocr_status = build_ocr_runtime(ctx)
    docs = [read_document(path, ocr_client=ocr_client) for path in iter_input_files(ctx["document_folder"])]
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc["kind"]] = counts.get(doc["kind"], 0) + 1
    return {
        "documents": docs,
        "document_count": len(docs),
        "kind_counts": counts,
        "source_refs": [doc["source_ref"] for doc in docs],
        "warnings": list(ocr_status.get("warnings") or []) + [warning for doc in docs for warning in doc.get("warnings", [])],
        "ocr": ocr_status,
        "ocr_required_sources": [doc["source_ref"] for doc in docs if doc.get("ocr_required")],
        "ocr_required_count": len([doc for doc in docs if doc.get("ocr_required")]),
    }

def step_bank_statement_extractor(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    statements = [doc for doc in docs if doc["kind"] == "bank_statement"]
    extracted = []
    totals = {"deposits": 0.0, "withdrawals": 0.0, "fees": 0.0}
    opening_balance = 0.0
    closing_balance = 0.0
    for doc in statements:
        text = doc.get("text") or ""
        transactions = []
        statement_context = extract_statement_context(text)
        opening_balance = opening_balance or extract_named_amount(text, ["opening balance"])
        closing_balance = closing_balance or extract_named_amount(text, ["closing balance"])
        for line_no, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            amount = amount_from_line(line)
            if amount is None:
                continue
            if "deposit" in lowered or "payroll" in lowered:
                direction = "deposit"
                totals["deposits"] += amount
            elif "fee" in lowered:
                direction = "fee"
                totals["fees"] += amount
            elif "withdrawal" in lowered or "payment" in lowered or "rent" in lowered or "bill" in lowered:
                direction = "withdrawal"
                totals["withdrawals"] += amount
            else:
                continue
            classification = classify_cash_transaction(line.strip(), direction)
            transactions.append(
                {
                    "source_ref": doc["source_ref"],
                    "line_no": line_no,
                    "description": line.strip(),
                    "amount": amount,
                    "direction": direction,
                    **classification,
                }
            )
        extracted.append(
            {
                "source_ref": doc["source_ref"],
                "opening_balance": opening_balance,
                "closing_balance": closing_balance,
                **statement_context,
                "transactions": transactions,
            }
        )
    all_transactions = [item for statement in extracted for item in statement.get("transactions", [])]
    pending_classification_total = sum(
        float(item.get("amount") or 0.0)
        for item in all_transactions
        if item.get("classification_status") == "pending_customer_confirmation"
    )
    fee_total = float(totals.get("fees") or 0.0)
    fee_transactions = [item for item in all_transactions if item.get("direction") == "fee"]
    statement_periods = [statement.get("statement_period") for statement in extracted if statement.get("statement_period")]
    account_names = sorted({str(statement.get("account_name")) for statement in extracted if statement.get("account_name")})
    return {
        "statement_count": len(statements),
        "statements": extracted,
        "totals": totals,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "net_cash_flow": totals["deposits"] - totals["withdrawals"] - totals["fees"],
        "statement_periods": statement_periods,
        "account_names": account_names,
        "account_coverage": "one_statement_and_one_account" if len(extracted) == 1 and len(account_names) <= 1 else "partial_or_multiple_accounts",
        "pending_classification_total": round(pending_classification_total, 2),
        "fee_review": {
            "fee_total": round(fee_total, 2),
            "fee_count": len(fee_transactions),
            "recurrence_status": "not_established" if fee_transactions else "not_detected",
            "annual_cost_if_monthly": round(fee_total * 12, 2) if fee_transactions else 0.0,
            "waiver_terms_status": "not_provided",
        },
        "warnings": [] if statements else ["no_bank_statement_detected"],
    }

__all__ = ["step_bank_statement_extractor", "step_financial_document_reader", "step_financial_folder_watcher"]
