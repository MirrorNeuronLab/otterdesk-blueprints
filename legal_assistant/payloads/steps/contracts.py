from __future__ import annotations

from mn_sdk.step_runtime import StepContext

from runtime import runtime
from ._state import build_stage_context, result


def run(context: StepContext, operation: str) -> dict:
    ctx = build_stage_context(context)
    records = ctx["state"].get("records") or []
    if operation == "extract":
        packet = runtime.extract_contract_clause_packet(records)
        ctx["state"]["clause_packet"] = packet
        return result(ctx, clause_count=packet.get("clause_count", 0))
    if operation == "compare":
        packet = ctx["state"].get("clause_packet") or runtime.extract_contract_clause_packet(records)
        clause_types = [str(item.get("clause_type")) for item in packet.get("clauses") or [] if isinstance(item, dict)]
        comparison = runtime.compare_to_playbook(clause_types)
        ctx["state"]["playbook_comparison"] = comparison
        return result(ctx, comparison=comparison)
    raise ValueError(f"unknown legal contract operation: {operation}")
