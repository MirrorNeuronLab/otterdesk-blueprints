"""Versioned procurement case evaluation from a selected local case document."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import append_human_event, read_human_events

from .procurement_decision import evaluate_case
from .state import _state


CASE_PACKET = "procurement_case_packet.json"


def render_case_packet(packet: dict[str, Any]) -> str:
    lines = [
        "# Procurement approval packet — draft for review", "",
        f"- Case: {packet.get('case_id') or 'Unassigned'}; revision: {packet.get('revision')}",
        f"- Mode: {packet.get('mode')}; as of: {packet.get('as_of')}",
        f"- Status: {packet.get('status')}; approvals: {packet.get('review_status')}",
        f"- Decision digest: {packet.get('decision_digest')}",
        f"- Proposed supplier: {packet.get('selected_supplier_id') or 'None'}",
        f"- Required reviews: {', '.join(packet.get('required_reviewers') or []) or 'None recorded'}",
        "", "| Supplier | Outcome | Fit | Cash due at order | Known horizon cost | Evidence |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for outcome in packet.get("quote_outcomes") or []:
        cost = outcome.get("cost") or {}
        lines.append(f"| {outcome.get('supplier_name') or outcome.get('supplier_id')} | {outcome.get('outcome')} | {(outcome.get('fit') or {}).get('status') or 'Unknown'} | {cost.get('cash_due_at_order') or 'Unknown'} | {cost.get('known_cost_over_comparison_horizon') or 'Unknown'} | {', '.join(outcome.get('evidence_refs') or []) or 'None'} |")
    lines.extend(["", *[f"- {item}" for item in packet.get("limitations") or []], ""])
    lines.append("Simulation values are fictional. No supplier contact or order occurred." if packet.get("mode") == "MOCK" else "Draft only. OtterDesk did not contact suppliers or place an order.")
    return "\n".join(lines) + "\n"


def selected_case_mode(documents: list[dict[str, Any]]) -> str | None:
    for item in documents:
        if Path(str(item.get("name") or "")).name != "procurement_case.json":
            continue
        try:
            value = json.loads(item.get("text") or "{}")
            return str(value.get("mode") or "MOCK") if isinstance(value, dict) else "MOCK"
        except (TypeError, ValueError):
            return "MOCK"
    return None


def assess_procurement_case(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    documents = _state(ctx).get("documents") or []
    selected = [item for item in documents if Path(str(item.get("name") or "")).name == "procurement_case.json"]
    if not selected:
        return {"status": "NOT_PROVIDED", "case_packet": None}
    if len(selected) != 1:
        raise ValueError("Select exactly one procurement_case.json document")
    case = json.loads(selected[0].get("text") or "{}")
    if not isinstance(case, dict):
        raise ValueError("procurement_case.json must contain an object")
    packet = evaluate_case(case)
    packet["source_ref"] = selected[0].get("source_ref")
    packet["schema_version"] = "otterdesk.procurement.case_packet.v1"
    target = Path(ctx["run_dir"]) / "workflow_state" / CASE_PACKET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": packet["status"], "case_packet": str(target), "decision_digest": packet.get("decision_digest")}


def emit_review_requests(ctx: dict[str, Any], packet: dict[str, Any]) -> list[str]:
    """Publish exact-packet review actions to OtterDesk's existing conversation panel."""
    if packet.get("status") != "READY_FOR_REVIEW" or not packet.get("decision_digest"):
        return []
    run_id = ctx["run_id"]
    runs_root = Path(ctx["run_dir"]).parent
    existing = {
        str((event.get("payload") or {}).get("request_id"))
        for event in read_human_events(run_id, runs_root=runs_root)
        if event.get("type") == "human_input_requested"
    }
    emitted: list[str] = []
    for reviewer in packet.get("required_reviewers") or []:
        if packet.get("mode") == "MANUAL" and reviewer != "owner":
            continue  # A local click cannot impersonate an outside reviewer.
        request_id = f"procurement-{packet['case_id']}-r{packet['revision']}-{reviewer}-{packet['decision_digest'][:16]}"
        if request_id in existing:
            continue
        selected = next((item for item in packet.get("quote_outcomes") or [] if item.get("supplier_id") == packet.get("selected_supplier_id")), {})
        cost = selected.get("cost") or {}
        prompt = (
            f"{'Simulated ' if packet.get('mode') == 'MOCK' else 'Local owner '}"
            f"{reviewer} review for case {packet['case_id']} revision {packet['revision']}. "
            f"Proposed supplier: {selected.get('supplier_name') or packet.get('selected_supplier_id')}; "
            f"cash due at order {cost.get('currency')} {cost.get('cash_due_at_order')}; "
            f"known {cost.get('horizon_months')}-month cost {cost.get('currency')} {cost.get('known_cost_over_comparison_horizon')}. "
            f"Decision digest: {packet['decision_digest']}. "
            "This review does not authorize supplier contact or an order."
        )
        append_human_event(
            run_id, "human_input_requested",
            {"request_id": request_id, "prompt": prompt, "options": ["Approve", "Request changes", "Reject"], "decision_type": "procurement_review", "decision_digest": packet["decision_digest"], "case_id": packet["case_id"], "revision": packet["revision"], "reviewer": reviewer, "mode": packet["mode"]},
            runs_root=runs_root, blueprint_id="purchasing_manager",
        )
        emitted.append(request_id)
    return emitted
