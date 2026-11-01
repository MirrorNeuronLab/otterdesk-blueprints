"""Procurement-specific questions at a completed, evidence-backed handoff."""
from __future__ import annotations

from typing import Any

from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.blueprint_support import append_human_event, read_human_events

from .common import BLUEPRINT_ID


REVIEW_EFFECT = "Your response records a review of this saved packet. It does not change the report, start another run, contact suppliers or place an order."


def case_review_question(packet: dict[str, Any], reviewer: str) -> dict[str, Any]:
    selected = next((item for item in packet.get("quote_outcomes") or []
                     if item.get("supplier_id") == packet.get("selected_supplier_id")), {})
    cost = selected.get("cost") or {}
    supplier = selected.get("supplier_name") or packet.get("selected_supplier_id") or "the proposed supplier"
    questions = {
        "owner": ("Review purchase fit", f"Does {supplier}'s quoted configuration meet the purchase brief and mandatory requirements?", "The comparable quotes are ready; the purchase owner needs to confirm the proposed fit."),
        "finance": ("Review cost and cash commitment", f"Are {supplier}'s cash due at order, support payments and known horizon cost acceptable for this case?", "The selected quote triggers the case's finance review policy. Unknown costs still need separate assessment."),
        "legal": ("Review supplier and terms", f"Are {supplier}'s vendor status, warranty and commercial terms acceptable, or what needs to change?", "The selected supplier requires review under the case's vendor policy."),
        "security": ("Review sensitive data requirements", f"Does {supplier}'s proposal meet the sensitive data requirements, or what evidence is missing?", "This case involves sensitive data and its policy requires security review."),
    }
    summary, prompt, why = questions.get(reviewer, (f"Review {reviewer} requirements", f"Can the proposed {supplier} packet pass your {reviewer} review?", "The case policy requires this review."))
    return {
        "summary": ("Simulation: " if packet.get("mode") == "MOCK" else "") + summary,
        "prompt": prompt,
        "interaction_kind": "approval",
        "blocking": False,
        "why_now": why,
        "context": [
            {"label": "Why now", "value": why},
            {"label": "Proposed supplier", "value": str(supplier)},
            {"label": "Cash due at order", "value": f"{cost.get('currency')} {cost.get('cash_due_at_order')}"},
            {"label": "Known comparison cost", "value": f"{cost.get('currency')} {cost.get('known_cost_over_comparison_horizon')} over {cost.get('horizon_months')} months; excludes energy, resale value and downtime."},
            {"label": "Evidence", "value": ", ".join(selected.get("evidence_refs") or []) or "No source reference recorded"},
            {"label": "Review scope", "value": REVIEW_EFFECT},
        ],
        "options": [
            {"label": "Approve", "description": "Record agreement with this packet for this review role only."},
            {"label": "Request changes", "description": "Record what must change. Update the inputs and start a new run to revise the packet."},
            {"label": "Reject", "description": "Record that this packet is not acceptable for this review role."},
        ],
    }


def build_human_review(artifact: dict[str, Any]) -> dict[str, Any]:
    """Choose one material next question; never ask for approval of missing evidence."""
    case = artifact.get("procurement_case")
    if isinstance(case, dict):
        status = case.get("status")
        if status == "READY_FOR_REVIEW" and case.get("required_reviewers"):
            reviewers = case["required_reviewers"]
            reviewer = "owner" if "owner" in reviewers else reviewers[0]
            review = case_review_question(case, reviewer)
            return {**review, "stage": "packet_review", "required_reviewers": reviewers,
                    "next_step": "Record each required review. Changes to the purchasing inputs require a new run and a fresh packet review."}
        kind = "missing_information"
        if status == "WAITING_FOR_USER":
            summary = "Confirm the review policy"
            prompt = "Which company review policy should govern this purchase?"
            why = case.get("reason") or "A manual case needs a confirmed policy before quotes can be evaluated."
            next_step = "Add and confirm the policy in procurement_case.json, then start a new run. A reply alone does not confirm the policy."
        elif status == "WAITING_FOR_EXTERNAL":
            summary = "Resolve the outstanding quote"
            prompt = "Should the next comparison wait for the outstanding quote, or use a revised supplier list?"
            why = "At least one quote is outstanding in the case snapshot. This completed run is not watching for supplier replies."
            next_step = "Update the case with the quote or revised supplier list, then start a new run."
        elif status == "READY_FOR_REVIEW":
            kind = "judgment"
            summary = "Review the purchase brief"
            prompt = "Does the proposed supplier meet your purchase brief, or what needs to change?"
            why = "The case has comparable quotes but no required review roles are recorded."
            next_step = "Review the packet and confirm the applicable review policy before any commitment outside this co-worker."
        else:
            summary = "Provide comparable quote evidence"
            prompt = "Can you provide a current quote that meets the mandatory requirements and cash cap, including shipping, tax and support?"
            why = "The case does not have enough comparable quotes. See each supplier's reason in the comparison."
            next_step = "Update the quote evidence or correct the purchasing requirements, then start a new run."
        return {"stage": "clarification" if kind == "missing_information" else "shortlist_review", "summary": summary, "prompt": prompt, "why_now": why,
                "next_step": next_step, "interaction_kind": kind, "blocking": False, "options": [],
                "context": [{"label": "Why now", "value": why}, {"label": "Next step", "value": next_step},
                            {"label": "Review scope", "value": REVIEW_EFFECT}]}

    summary = artifact.get("procurement_summary") or {}
    preferred = summary.get("preferred_vendor") or artifact.get("preferred_candidate")
    gaps = artifact.get("evidence_gaps") or []
    if not preferred:
        title = "Resolve the comparison blocker"
        prompt = "Can you provide current quote evidence for an option that meets the purchase requirements, or explain which requirement needs correcting?"
        why = "No preferred option passed the comparison. Approval would be premature."
        kind, options = "missing_information", []
    elif summary.get("budget_status") == "not_set":
        title = "Set the purchase budget"
        prompt = "What is your maximum all-in purchase budget, or is this comparison still exploratory?"
        why = "A preferred option exists, but affordability has not been checked against a purchase ceiling."
        kind, options = "missing_information", []
    else:
        title = "Review the shortlist"
        prompt = f"Does the proposed {preferred} option meet your purchase brief, or what needs to change?"
        why = "The comparison is ready for your judgment. Resolve the listed evidence gaps and planning assumptions before a commitment."
        kind = "judgment"
        options = [
            {"label": "Keep this shortlist", "description": "Record this as the shortlist for human review; outstanding evidence and approvals remain."},
            {"label": "Request changes", "description": "Record the requirements, evidence or assumptions to change in the next run."},
            {"label": "Reject shortlist", "description": "Record that the compared options do not meet your needs."},
        ]
    next_step = "Record your response here. Change settings in Configure or update the source documents, then start a new run to revise the comparison."
    return {"stage": "clarification" if kind == "missing_information" else "shortlist_review",
            "summary": title, "prompt": prompt, "why_now": why, "interaction_kind": kind,
            "blocking": False, "options": options, "next_step": next_step,
            "context": [{"label": "Why now", "value": why},
                        *([{"label": "Evidence to resolve", "value": "; ".join(str(item) for item in gaps[:3])[:500]}] if gaps else []),
                        {"label": "Next step", "value": next_step}, {"label": "Review scope", "value": REVIEW_EFFECT}]}


def emit_handoff_question(block, artifact: dict[str, Any]) -> list[str]:
    """Publish the domain's one next question after the report has been committed."""
    review = artifact["human_review"]
    request_id = "procurement-handoff-" + fingerprint({"run_id": block.run_id, "review": review})[:32]
    runs_root = block.store.run_dir.parent
    if any(event.get("type") == "human_input_requested" and (event.get("payload") or {}).get("request_id") == request_id
           for event in read_human_events(block.run_id, runs_root=runs_root)):
        return []
    append_human_event(block.run_id, "human_input_requested",
                       {**review, "request_id": request_id, "decision_type": "procurement_handoff"},
                       runs_root=runs_root, blueprint_id=BLUEPRINT_ID)
    return [request_id]
