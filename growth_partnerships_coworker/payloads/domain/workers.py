from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from mn_marketing_email_skill import compose_text_body, normalize_structured_draft, review_email_quality
from mn_market_research_skill import build_research_brief
from mn_sdk.blueprint_support.workflow_state import write_json

from .collaboration import build_packet, persist_packet, write_final_artifact
from .delivery import deliver_approved_development_email
from .inputs import csv_rows, normalized_inputs, resolve_input_file, source_descriptor


PRIVATE_QUEUE_PATH = "confidential_outreach_queue.json"


def run_growth_lead(context: dict[str, Any], *, step_id: str, **_: Any) -> dict[str, Any]:
    if step_id == "qualify_seed_contacts":
        return _qualify_seed_contacts(context)
    if step_id == "publish_gtm_outreach_queue":
        return _publish_gtm_packet(context)
    if step_id == "deliver_approved_email":
        return _deliver_approved_email(context)
    raise ValueError(f"Growth & Partnerships co-worker does not own step {step_id!r}")


def _qualify_seed_contacts(context: dict[str, Any]) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    business_name = str(inputs["business_name"])
    contacts_path = resolve_input_file(context, "contacts_csv", "edtech_contacts_sample.csv")
    contacts = csv_rows(contacts_path)
    synthetic = _is_synthetic_source(context, contacts_path)
    settings = (context.get("config") or {}).get("gtm") or {}
    max_contacts = max(1, min(int(settings.get("max_contacts_per_run", 100)), 500))
    ranked = sorted((_contact_candidate(row) for row in contacts), key=lambda item: (-item["priority_score"], item["contact_id"]))
    queue = [_draft_contact(candidate, business_name=business_name) for candidate in ranked[:max_contacts]]
    category_counts = Counter(item["category"] for item in ranked)
    quality_pass_count = sum(1 for item in queue if item["draft_review"]["approved"])
    queue_artifact = {
        "schema_version": "mn.business_growth.confidential_outreach_queue.v1",
        "classification": "confidential_contact_data",
        "source_ref": f"input:{contacts_path.name}",
        "mode": "draft_only",
        "send_authorized": False,
        "total_seed_contacts": len(contacts),
        "queued_contacts": len(queue),
        "contacts": queue,
    }
    write_json(Path(context["run_dir"]) / PRIVATE_QUEUE_PATH, queue_artifact)
    packet = build_packet(
        context,
        stage="qualify_seed_contacts",
        objective="Turn approved adult professional seed contacts into a researched, relevance-ranked GTM queue without sending outreach.",
        trigger="Founder supplies an approved first-party or public-source contact CSV.",
        sources=[source_descriptor(contacts_path, synthetic=synthetic)],
        observed_facts=[
            f"The supplied seed file contains {len(contacts)} non-empty contact rows.",
            f"The source categories contain {category_counts.get('investor', 0)} investor, {category_counts.get('client', 0)} client, and {category_counts.get('other', 0)} other records.",
            f"The draft-only queue contains {len(queue)} contacts; {quality_pass_count} drafts passed deterministic copy checks.",
        ],
        assumptions=[
            "A record in the seed file does not by itself establish consent, legitimate interest, relevance, or deliverability.",
            "Heuristic categories and notes require human research before outreach.",
        ],
        analysis={
            "category_counts": dict(category_counts),
            "queued_contact_count": len(queue),
            "draft_quality_pass_count": quality_pass_count,
            "contacts_requiring_research": category_counts.get("other", 0),
            "private_queue_artifact": PRIVATE_QUEUE_PATH,
            "confidential_fields_excluded_from_response_context": ["name", "email", "note", "individual draft body"],
            "research_brief": build_research_brief(
                f"{business_name} customer, creator, community, distribution, and investor partnership outreach",
                audience="Adult professionals and potential business partners",
                competitors=["customer status quo", "manual alternatives", "direct and adjacent competitors"],
            ),
        },
        recommendation="Research the highest-fit education customers first, then a small investor-learning cohort; keep general contacts on hold until relevance is established.",
        confidence="low" if synthetic or category_counts.get("other", 0) > len(contacts) / 2 else "medium",
        risks=[
            f"Irrelevant cold outreach can harm {business_name}'s reputation and sender deliverability.",
            "Contact data may be stale or lack an appropriate outreach basis.",
            "Marketing claims about learning outcomes require evidence and approval.",
        ],
        requested_approval=[
            "Approve the lawful basis, relevance research, sender identity, and each initial outreach batch before sending.",
            "Approve all product, learning, pricing, and investment claims in the draft copy.",
        ],
        outputs=["confidential ranked outreach queue", "per-contact draft copy", "aggregate GTM work packet"],
        next_check="After a human reviews the first ten contacts and records reply, opt-out, and relevance outcomes.",
    )
    return {**persist_packet(context, packet), "private_queue_artifact": PRIVATE_QUEUE_PATH}


def _publish_gtm_packet(context: dict[str, Any]) -> dict[str, Any]:
    queue = _read_json(Path(context["run_dir"]) / PRIVATE_QUEUE_PATH)
    contacts = queue.get("contacts") if isinstance(queue.get("contacts"), list) else []
    approved_drafts = sum(1 for item in contacts if isinstance(item, dict) and (item.get("draft_review") or {}).get("approved"))
    packet = build_packet(
        context,
        stage="publish_gtm_outreach_queue",
        objective="Publish an approval-ready GTM operating packet while keeping contact identities in a local confidential artifact.",
        trigger="Seed qualification and draft quality checks are complete.",
        sources=[{"source_ref": str(queue.get("source_ref") or "input:contacts.csv"), "data_quality_note": "Contact details remain in a confidential run artifact."}],
        observed_facts=[
            f"The local queue contains {len(contacts)} draft-only contact records.",
            f"{approved_drafts} drafts passed deterministic placeholder and structure checks.",
        ],
        assumptions=["No message has been sent and no contact is treated as opted in."],
        analysis={
            "private_queue_artifact": PRIVATE_QUEUE_PATH,
            "queued_contact_count": len(contacts),
            "draft_quality_pass_count": approved_drafts,
            "send_authorized": False,
        },
        recommendation="Approve a manually researched ten-contact pilot, measure qualified replies and opt-outs, and expand only if relevance and trust guardrails hold.",
        confidence="low",
        risks=["The seed classifications are heuristic.", "Bulk sending remains prohibited."],
        requested_approval=["Founder approves the specific recipients, copy, lawful basis, and send mechanism for the pilot."],
        outputs=["GTM decision packet", "confidential outreach queue"],
        next_check="After the approved pilot's response window closes.",
        publication_state="staged",
    )
    return persist_packet(context, packet)


def _deliver_approved_email(context: dict[str, Any]) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    business_name = str(inputs["business_name"])
    queue = _read_json(Path(context["run_dir"]) / PRIVATE_QUEUE_PATH)
    contacts = queue.get("contacts") if isinstance(queue.get("contacts"), list) else []
    approved_drafts = sum(1 for item in contacts if isinstance(item, dict) and (item.get("draft_review") or {}).get("approved"))
    delivery = deliver_approved_development_email(context, queue)
    delivered = delivery.get("status") in {"sent", "already_sent"}
    packet = build_packet(
        context,
        stage="deliver_approved_email",
        objective="Apply an explicitly approved development email send while keeping queued contact identities private and bulk delivery blocked.",
        trigger="The approval-ready outreach queue is published and SMTP delivery policy is evaluated.",
        sources=[{"source_ref": str(queue.get("source_ref") or "input:contacts.csv"), "data_quality_note": "Contact details remain in a confidential run artifact and are never used as development recipients."}],
        observed_facts=[
            f"The local queue contains {len(contacts)} draft-only contact records.",
            f"{approved_drafts} drafts passed deterministic placeholder and structure checks.",
            (
                "One explicitly approved development test email was delivered; no queued contact address was used."
                if delivered
                else "No email was delivered because SMTP delivery is disabled or explicit approval is absent."
            ),
        ],
        assumptions=["A successful development delivery does not authorize production outreach or establish a lawful basis for contacting queued recipients."],
        analysis={
            "private_queue_artifact": PRIVATE_QUEUE_PATH,
            "delivery_receipt_artifact": delivery.get("receipt_artifact") or "not_created",
            "queued_contact_count": len(contacts),
            "draft_quality_pass_count": approved_drafts,
            "delivery_status": delivery.get("status"),
            "delivery_mode": delivery.get("mode"),
            "delivered_recipient_count": int(delivery.get("recipient_count") or 0),
            "queued_contact_addresses_used": False,
        },
        recommendation=(
            "Review the development message rendering and delivery receipt before authorizing any separately implemented production pilot."
            if delivered
            else "Keep outreach in draft-only mode until a human supplies explicit approval and the development SMTP secret environment is configured."
        ),
        confidence="medium" if delivered else "low",
        risks=[
            "SMTP cannot guarantee exactly-once delivery after an interrupted network transaction.",
            "A development delivery must never be treated as approval for queued production contacts.",
            "Bulk sending and production list delivery remain prohibited.",
        ],
        requested_approval=(
            []
            if delivered
            else ["Founder supplies a bounded approval_id and approves one development delivery after reviewing the draft and sender identity."]
        ),
        outputs=["GTM decision packet", "confidential outreach queue", "confidential SMTP delivery receipt"],
        next_check=(
            "After the test recipient confirms rendering and receipt."
            if delivered
            else "After a human reviews the draft and configures the development-only SMTP environment."
        ),
        publication_state="final",
    )
    persisted = persist_packet(context, packet)
    final = write_final_artifact(
        context,
        packet,
        artifact_type="growth_partnerships_operating_brief",
        executive_summary=(
            f"The Growth & Partnerships co-worker converted {business_name}'s supplied adult-professional seed list into a confidential queue and delivered one explicitly approved development test email. No queued contact address was used."
            if delivered
            else f"The Growth & Partnerships co-worker converted {business_name}'s supplied adult-professional seed list into a confidential, draft-only queue and an aggregate approval packet. No outreach was sent."
        ),
        evidence={
            "seed_contact_count": queue.get("total_seed_contacts", 0),
            "queued_contact_count": len(contacts),
            "draft_quality_pass_count": approved_drafts,
            "private_queue_artifact": PRIVATE_QUEUE_PATH,
            "delivery_status": delivery.get("status"),
            "delivery_mode": delivery.get("mode"),
            "delivered_recipient_count": int(delivery.get("recipient_count") or 0),
            "delivery_receipt_artifact": delivery.get("receipt_artifact") or "not_created",
            "privacy_note": "Names, email addresses, source notes, and individual drafts remain only in confidential run artifacts and are excluded from response context.",
        },
        next_steps=[
            "Manually research the first ten education-sector contacts for relevance and lawful outreach basis.",
            "Review and revise every draft before sending.",
            "Record replies, opt-outs, qualified conversations, and downstream activation evidence.",
            "Record aggregate channel, objection, and conversion findings as human-reviewed cross-functional handoffs.",
        ],
        data_status=str(queue.get("classification") or "unknown"),
        role_contribution="Create a repeatable path to qualified demand and distribution while protecting brand trust, contact privacy, and cash.",
        north_star_question="Which customer or partner channel produces retained, evidence-backed value at an affordable acquisition cost?",
        role_scorecard=[
            {"metric": "pilot_contacts_ready", "current": len(contacts), "target": "10 manually researched contacts", "decision_use": "Confirm the first learning cohort is small and reviewable."},
            {"metric": "draft_quality_pass_rate", "current": round(approved_drafts / len(contacts), 3) if contacts else 0, "target": 1.0, "decision_use": "Do not test copy that fails deterministic quality checks."},
            {"metric": "qualified_reply_rate", "current": "not_measured", "target": "measure after approved pilot", "decision_use": "Continue only where conversations are relevant and voluntary."},
            {"metric": "retained_customer_cac", "current": "needs Finance and Lifecycle evidence", "target": "within Finance-approved CAC and payback guardrails", "decision_use": "Scale channels only after retention evidence exists."},
        ],
        founder_decisions=[
            {"decision": "Approve or reject the first ten-contact pilot", "why_now": "The queue and drafts are ready, but lawful basis, recipient relevance, claims, and sender identity require human judgment."},
            {"decision": "Choose the primary learning channel", "why_now": "A single audience and offer produces interpretable evidence; parallel broad outreach would not."},
            {"decision": "Set the stop rule", "why_now": "Pause if relevance, opt-out, trust, CAC, or safety thresholds fail."},
        ],
        cross_functional_handoffs=[
            {"to": "business_finance_controller", "provides": "channel-level qualified-conversation and acquisition evidence", "needs_from": "maximum CAC, payback, and experiment cash limits"},
            {"to": "customer_lifecycle_director", "provides": "prospect objections and segment language", "needs_from": "retained-customer segments, activation friction, and churn evidence"},
            {"to": "learning_quality_safety_director", "provides": "claims proposed in outreach", "needs_from": "approved claim language and blocked promise categories"},
            {"to": "content_studio_director", "provides": "audience and channel proof-asset requirements", "needs_from": "approved demo assets and production lead times"},
        ],
        ninety_day_plan=[
            {"days": "0-30", "outcome": "Research and run one approved ten-contact customer-learning pilot; record replies, objections, opt-outs, and next steps."},
            {"days": "31-60", "outcome": "Repeat only the strongest segment-message pair and validate handoff from conversation to first product value."},
            {"days": "61-90", "outcome": "Recommend scale, revise, or stop using retained conversion, CAC, payback, trust, and safety evidence from peer roles."},
        ],
        recommended_action_status=(
            "development_test_delivered" if delivered else "awaiting_human_approval"
        ),
    )
    return {**persisted, **final}


def _contact_candidate(row: dict[str, str]) -> dict[str, Any]:
    email = str(row.get("Email") or row.get("email") or "").strip().lower()
    name = str(row.get("Name") or row.get("name") or "").strip()
    category = str(row.get("Category") or row.get("category") or "other").strip().lower()
    if category not in {"client", "investor", "other"}:
        category = "other"
    note = str(row.get("Note") or row.get("note") or "").strip()
    highlight = str(row.get("Highlight") or row.get("highlight") or "").strip()
    base = {"client": 90, "investor": 75, "other": 30}[category]
    signal = f"{note} {highlight}".lower()
    if any(term in signal for term in ("edu", "learn", "school", "teacher", "library")):
        base += 8
    if any(term in signal for term in ("news", "substack", "creator", "community")):
        base += 5
    return {
        "contact_id": f"contact-{hashlib.sha256(email.encode('utf-8')).hexdigest()[:16]}",
        "name": name,
        "email": email,
        "category": category,
        "note": note,
        "highlight": highlight,
        "priority_score": min(base, 100),
        "research_required": True,
    }


def _draft_contact(candidate: dict[str, Any], *, business_name: str) -> dict[str, Any]:
    category = candidate["category"]
    first_name = str(candidate.get("name") or "there").split()[0]
    angle = {
        "client": "a short conversation about the customer problem, current alternatives, and desired outcome",
        "investor": f"a short conversation about {business_name}'s product and evidence plan",
        "other": f"a relevance check before proposing any {business_name} collaboration",
    }[category]
    draft = normalize_structured_draft(
        {
            "subject_candidates": [
                f"A focused {business_name} conversation",
                "Exploring a useful collaboration",
            ],
            "preview_text": "A short, adult-directed note to confirm relevance before discussing the business.",
            "body_sections": [
                {
                    "title": f"Hi {first_name}",
                    "body": f"I'm working on {business_name}, and I am reaching out to learn whether its customer problem and evidence plan are relevant to your work.",
                },
                {
                    "title": "Why I'm reaching out",
                    "body": f"Your record suggests {angle}. I would first like to confirm whether this is relevant to your work.",
                },
                {
                    "title": "A small next step",
                    "body": f"If relevant, would you be open to a brief conversation about the problem, current alternatives, and the evidence you would need to take {business_name} seriously?",
                },
            ],
            "cta_label": "Reply if relevant",
            "footer": "Draft only — requires human review and an appropriate outreach basis before sending.",
        }
    )
    body = compose_text_body(**draft)
    review = review_email_quality(
        draft=draft,
        forbidden_phrases=("guaranteed learning", "therapy", "diagnose", "cure"),
    )
    return {
        **candidate,
        "outreach_status": "awaiting_human_research_and_approval",
        "draft": {"subject": draft["subject"], "body": body},
        "draft_review": review,
    }


def _is_synthetic_source(context: dict[str, Any], path: Path) -> bool:
    try:
        return path.is_relative_to(Path(context["blueprint_dir"]).resolve())
    except (AttributeError, ValueError):
        return str(path).startswith(str(Path(context["blueprint_dir"]).resolve()))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
