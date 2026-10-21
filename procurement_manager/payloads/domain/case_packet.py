"""Versioned procurement case evaluation from a selected local case document."""
from __future__ import annotations

from mn_sdk.agent_events import report_activity

import json
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import append_human_event, read_human_events

from .procurement_decision import evaluate_case
from .state import read_state
from .common import BLUEPRINT_ID


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


def assess_procurement_case(block, inputs) -> dict[str, Any]:
    report_activity("Assessing the procurement case", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    documents = read_state(block, inputs["previous"]).get("documents") or []
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
    reference = block.store.commit("workflow_state/" + CASE_PACKET, packet, kind="procurement_case_packet")
    return {"status": packet["status"], "case_packet": reference.to_dict(), "decision_digest": packet.get("decision_digest")}


def verified_case_packet(block, summary):
    if not isinstance(summary, dict) or "case_packet" not in summary:
        raise ValueError("Report publication requires a verified case assessment")
    reference = summary["case_packet"]
    path = "workflow_state/" + CASE_PACKET
    if reference is None:
        if block.store.path(path).exists():
            raise ValueError("An absent case assessment cannot publish a stale case packet")
        return None
    if reference.get("path") != path:
        raise ValueError("Case assessment points to a different packet")
    packet = block.store.read(reference)
    if packet["status"] != summary["status"] or packet.get("decision_digest") != summary.get("decision_digest"):
        raise ValueError("Case packet differs from its assessment")
    return packet


def emit_review_requests(block, packet: dict[str, Any]) -> list[str]:
    """Publish exact-packet review actions to OtterDesk's existing conversation panel."""
    if packet.get("status") != "READY_FOR_REVIEW" or not packet.get("decision_digest"):
        return []
    run_id = block.run_id
    runs_root = Path(block.store.run_dir).parent
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
            runs_root=runs_root, blueprint_id=BLUEPRINT_ID,
        )
        emitted.append(request_id)
    return emitted
