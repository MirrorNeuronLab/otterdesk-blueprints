from __future__ import annotations

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime
from ._state import build_stage_context, result


def run(context: StepContext, operation: str) -> dict:
    ctx = build_stage_context(context)
    records = ctx["state"].get("records") or []
    if operation == "extract":
        packet = runtime.extract_invoice_bill_packet(records)
        ctx["state"]["invoice_packet"] = packet
        return result(ctx, invoice_count=packet.get("invoice_count", 0))
    if operation == "validate":
        packet = ctx["state"].get("invoice_packet") or runtime.extract_invoice_bill_packet(records)
        missing = runtime.missing_invoice_fields(packet.get("invoices") or [])
        ctx["state"]["invoice_validation"] = {"missing_fields": missing, "valid": not missing}
        return result(ctx, missing_field_count=len(missing), valid=not missing)
    raise ValueError(f"unknown legal invoice operation: {operation}")
