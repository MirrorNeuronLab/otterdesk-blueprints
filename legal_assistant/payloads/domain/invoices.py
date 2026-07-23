"""Invoice extraction, payable validation, and durable lane operations."""

from __future__ import annotations

from .common import *
from .documents import extract_named_value, find_amount, flatten_json, invoice_records
from .state import load_state, save_state

def extract_invoice_bill_packet(records: list[dict[str, Any]]) -> dict[str, Any]:
    invoices = []
    total_amount = 0.0
    for record in invoice_records(records):
        text = str(record.get("text") or "")
        flat = flatten_json(text)
        amount = flat.get("total_amount") or flat.get("invoice.total_amount") or find_amount(text)
        try:
            numeric_amount = float(str(amount).replace("$", "").replace(",", "")) if amount not in (None, "") else None
        except ValueError:
            numeric_amount = None
        if numeric_amount is not None:
            total_amount += numeric_amount
        invoice = {
            "source": record.get("filename"),
            "supplier_name": flat.get("supplier_name") or extract_named_value(text, ["supplier_name", "supplier", "vendor"]),
            "customer_name": flat.get("customer_name") or extract_named_value(text, ["customer_name", "customer", "bill_to"]),
            "invoice_id": flat.get("invoice_id") or extract_named_value(text, ["invoice_id", "invoice number", "invoice"]),
            "tax_id": flat.get("tax_id") or extract_named_value(text, ["tax_id", "tax id"]),
            "due_date": flat.get("due_date") or extract_named_value(text, ["due_date", "due date"]),
            "total_amount": numeric_amount,
            "billing_period": flat.get("billing_period") or extract_named_value(text, ["billing_period", "billing period"]),
            "line_items": flat.get("line_items") or [],
            "consumption_fields": flat.get("consumption_fields") or {},
            "warnings": record.get("warnings") or [],
        }
        invoices.append(invoice)
    return {
        "schema_version": "mn.blueprint.legal_assistant.invoice_bill_extraction.v1",
        "invoice_count": len(invoices),
        "invoices": invoices,
        "totals": {"total_amount": round(total_amount, 2)},
        "missing_fields": missing_invoice_fields(invoices),
        "review_required": True,
    }

def missing_invoice_fields(invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = []
    for invoice in invoices:
        absent = [field for field in ("supplier_name", "invoice_id", "due_date", "total_amount") if not invoice.get(field)]
        if absent:
            missing.append({"source": invoice.get("source"), "fields": absent})
    return missing


def extract_invoices(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    packet = extract_invoice_bill_packet(state.get("records") or [])
    state["invoice_packet"] = packet
    save_state(ctx, state, "legal_invoice_lane.json")
    return {"invoice_count": packet.get("invoice_count", 0)}


def validate_payables(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    packet = state.get("invoice_packet") or extract_invoice_bill_packet(state.get("records") or [])
    missing = missing_invoice_fields(packet.get("invoices") or [])
    state["invoice_validation"] = {"missing_fields": missing, "valid": not missing}
    save_state(ctx, state, "legal_invoice_lane.json")
    return {"missing_field_count": len(missing), "valid": not missing}


__all__ = ["extract_invoices", "validate_payables"]
