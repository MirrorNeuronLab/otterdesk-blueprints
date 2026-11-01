"""Versioned procurement case evaluation from a selected local case document."""
from __future__ import annotations

from mn_sdk.agent_events import report_activity

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import append_human_event, read_human_events

from .procurement_decision import evaluate_case
from .state import read_state
from .common import BLUEPRINT_ID
from .supervision import REVIEW_EFFECT, build_human_review, case_review_question


CASE_PACKET = "procurement_case_packet.json"


def _text(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace(">", "&gt;")


def _amount(value: Any, currency: str) -> str:
    return f"{currency} {Decimal(str(value)):,.2f}" if value is not None else "Not quoted"


def quote_review_reason(outcome: dict[str, Any], requirements: dict[str, Any]) -> str:
    if outcome.get("outcome") == "NO_RESPONSE":
        return "No quote by the recorded deadline; no price or rejection is inferred."
    if outcome.get("outcome") == "WAITING_FOR_EXTERNAL":
        return "Quote outstanding in this snapshot; this run is not watching for a reply."
    reasons = []
    if outcome.get("validity") != "CURRENT":
        reasons.append("Quote expired" if outcome.get("validity") == "EXPIRED" else "Quote expiry unverified")
    reasons.extend(f"{key.replace('_', ' ')}: {value.lower()}" for key, value in (outcome.get("fit") or {}).get("checks", {}).items() if value != "PASS")
    cap = (outcome.get("policy") or {}).get("cash_cap_status")
    if cap != "PASS":
        reasons.append("Cash cap exceeded" if cap == "FAIL" else "Cash cap or cash due unverified")
    cost = outcome.get("cost") or {}
    missing = [item for item in cost.get("unknown_or_unquantified_cost_items") or [] if item in {"unit_price", "shipping", "tax", "required_support"}]
    if missing:
        reasons.append("Not quoted: " + ", ".join(item.replace("_", " ") for item in missing))
    if cost.get("currency") != requirements.get("currency"):
        reasons.append("Currency differs from the purchase brief")
    return "; ".join(reasons) or "Meets the recorded fit, cash cap, currency and quote-validity checks; human reviews remain."


def render_case_packet(packet: dict[str, Any]) -> str:
    outcomes = packet.get("quote_outcomes") or []
    selected = next((item for item in outcomes if item.get("supplier_id") == packet.get("selected_supplier_id")), {})
    cost = selected.get("cost") or {}
    requirements = packet.get("requirements") or {}
    currency = cost.get("currency") or requirements.get("currency") or ""
    review = build_human_review({"procurement_case": packet})
    supplier = selected.get("supplier_name") or packet.get("selected_supplier_id")
    lines = [
        "# Purchase review", "",
        "**Simulation: fictional suppliers and prices.**" if packet.get("mode") == "MOCK" else "**Draft for human review.**",
        "", "## Decision brief", "",
        f"**{_text(supplier)} has the lowest known cost among comparable quotes.** Human review is required; responses are recorded separately from this saved packet." if selected else "**No supplier is ready for a purchase decision.** " + _text(packet.get("reason") or review["why_now"]),
        "",
    ]
    if selected:
        lines.extend([
            f"- Cash due at order: **{_amount(cost.get('cash_due_at_order'), currency)}**.",
            f"- Known cost over {cost.get('horizon_months')} months: **{_amount(cost.get('known_cost_over_comparison_horizon'), currency)}**.",
            "- Known cost is a subtotal. Energy, resale value and downtime are unquantified; this is not complete total cost of ownership.",
        ])
        alternatives = [item for item in outcomes if item.get("comparable") and item is not selected]
        if alternatives:
            runner_up = min(alternatives, key=lambda item: Decimal(item["cost"]["known_cost_over_comparison_horizon"]))
            difference = Decimal(runner_up["cost"]["known_cost_over_comparison_horizon"]) - Decimal(cost["known_cost_over_comparison_horizon"])
            other = _text(runner_up.get('supplier_name') or runner_up['supplier_id'])
            lines.append(f"- {_amount(difference, currency)} lower known cost than {other} over the same horizon." if difference else f"- The same known cost as {other} over the same horizon; review the non-price tradeoffs.")
            cash_difference = Decimal(cost["cash_due_at_order"]) - Decimal(runner_up["cost"]["cash_due_at_order"])
            if cash_difference > 0:
                lines.append(f"- Upfront tradeoff: {_text(supplier)} needs {_amount(cash_difference, currency)} more cash at order than {other}. Compare the horizon costs as well as the upfront amounts.")
    lines.extend(["", "## Your next decision", "", f"**{_text(review['prompt'])}**", "", _text(review["why_now"]), "", _text(review["next_step"]), "", REVIEW_EFFECT,
                  "", "## Supplier comparison", "", "| Supplier | Fit | Cash due at order | Known horizon cost | Comparison |",
                  "| --- | --- | ---: | ---: | --- |"])
    for outcome in outcomes:
        cost = outcome.get("cost") or {}
        fit = {"PASS": "Meets requirements", "FAIL": "Does not meet requirements"}.get((outcome.get("fit") or {}).get("status"), "Unverified")
        comparison = "Comparable" if outcome.get("comparable") else "Quote outstanding" if outcome.get("outcome") == "WAITING_FOR_EXTERNAL" else "No response" if outcome.get("outcome") == "NO_RESPONSE" else "Not comparable"
        lines.append(f"| {_text(outcome.get('supplier_name') or outcome.get('supplier_id'))} | {fit} | {_amount(cost.get('cash_due_at_order'), cost.get('currency') or currency)} | {_amount(cost.get('known_cost_over_comparison_horizon'), cost.get('currency') or currency)} | {comparison} |")
    if not outcomes:
        lines.append("| No quotes evaluated | Unverified | Not quoted | Not quoted | Confirm policy first |")
    lines.extend(["", "### Why each option is here", ""])
    for outcome in outcomes:
        lines.append(f"- **{_text(outcome.get('supplier_name') or outcome.get('supplier_id'))}:** {_text(quote_review_reason(outcome, requirements))}")
    lines.extend(["", "## Required reviews", ""])
    for reviewer in packet.get("required_reviewers") or []:
        question = case_review_question(packet, reviewer)
        lines.append(f"- **{reviewer.capitalize()}:** {_text(question['prompt'])}")
    if not packet.get("required_reviewers"):
        lines.append("No reviews requested yet. Resolve the blocker or confirm the review policy first.")
    if packet.get("mode") == "MANUAL":
        lines.append("Only the local owner's review can be recorded here. Finance, legal and security reviews must be obtained from the responsible people outside this co-worker.")
    lines.extend(["", "## Evidence and limitations", ""])
    for outcome in outcomes:
        lines.append(f"- **{_text(outcome.get('supplier_name') or outcome.get('supplier_id'))}:** quote version {_text(outcome.get('quote_version') or 'not received')}; evidence: {_text(', '.join(outcome.get('evidence_refs') or []) or 'none')}. Deadline or expected availability: {_text(outcome.get('deadline') or outcome.get('expected_at') or 'see quote')}.")
    lines.extend(f"- {_text(item)}" for item in packet.get("limitations") or [])
    lines.extend(["", "## Packet details", "",
                  f"- Case: {_text(packet.get('case_id') or 'Unassigned')}; revision: {packet.get('revision')}",
                  f"- As of: {_text(packet.get('as_of') or 'Not recorded')}",
                  f"- Status at publication: {_text(packet.get('status'))}; review status: {_text(packet.get('review_status'))}",
                  f"- Decision digest: `{packet.get('decision_digest')}`", "",
                  "Simulation values are fictional. No supplier contact or order occurred." if packet.get("mode") == "MOCK" else "No supplier contact or order occurred."])
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
    reviewers = packet.get("required_reviewers") or []
    for reviewer in sorted(reviewers, key=lambda role: (role != "owner", role)):
        if packet.get("mode") == "MANUAL" and reviewer != "owner":
            continue  # A local click cannot impersonate an outside reviewer.
        request_id = f"procurement-{packet['case_id']}-r{packet['revision']}-{reviewer}-{packet['decision_digest'][:16]}"
        if request_id in existing:
            continue
        question = case_review_question(packet, reviewer)
        append_human_event(
            run_id, "human_input_requested",
            {**question, "request_id": request_id, "decision_type": "procurement_review", "decision_digest": packet["decision_digest"], "case_id": packet["case_id"], "revision": packet["revision"], "reviewer": reviewer, "mode": packet["mode"]},
            runs_root=runs_root, blueprint_id=BLUEPRINT_ID,
        )
        emitted.append(request_id)
    return emitted
