from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from mn_marketing_email_skill import normalize_structured_draft, review_email_quality
from mn_sdk.blueprint_support.workflow_state import write_json

from .collaboration import build_packet, peer_signals, persist_packet, write_final_artifact
from .inputs import csv_rows, normalized_inputs, resolve_input_file, source_descriptor


INTERVENTIONS_PATH = "draft_customer_interventions.json"


def run_customer_lifecycle_director(context: dict[str, Any], *, step_id: str, **_: Any) -> dict[str, Any]:
    if step_id == "diagnose_customer_journey":
        return _diagnose_customer_journey(context)
    if step_id == "publish_customer_lifecycle_packet":
        return _publish_lifecycle_packet(context)
    raise ValueError(f"Customer Lifecycle co-worker does not own step {step_id!r}")


def _dataset(context: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any], bool]:
    path = resolve_input_file(context, "customer_feedback_file", "parent_feedback.csv")
    rows = csv_rows(path)
    synthetic = any(str(row.get("data_status") or "").lower() == "synthetic_demo" for row in rows)
    return rows, source_descriptor(path, synthetic=synthetic), synthetic


def _diagnose_customer_journey(context: dict[str, Any]) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    business_name = str(inputs["business_name"])
    rows, source, synthetic = _dataset(context)
    theme_counts = Counter(str(row.get("theme") or "unknown") for row in rows)
    stage_counts = Counter(str(row.get("journey_stage") or "unknown") for row in rows)
    interventions = [_intervention(theme, count, business_name=business_name) for theme, count in theme_counts.most_common(5)]
    write_json(
        Path(context["run_dir"]) / INTERVENTIONS_PATH,
        {
            "schema_version": "mn.customer_lifecycle.interventions.v1",
            "mode": "draft_only",
            "send_authorized": False,
            "interventions": interventions,
        },
    )
    peers = peer_signals(context)
    packet = build_packet(
        context,
        stage="diagnose_customer_journey",
        objective="Identify the activation, retention, support, and value-proof friction that prevents customers from reaching sustained value.",
        trigger="De-identified customer feedback or lifecycle observations are supplied.",
        sources=[source],
        observed_facts=[
            f"The supplied feedback set contains {len(rows)} records.",
            f"Theme counts are {dict(theme_counts)}.",
            f"Journey-stage counts are {dict(stage_counts)}.",
        ],
        assumptions=["Frequency in a small or synthetic feedback set is not population prevalence.", "The unchanged Bibblio demo happens to contain parent feedback; other businesses may supply their own customer vocabulary.", "Draft interventions must be tested against behavioral cohorts before automation."],
        analysis={
            "theme_counts": dict(theme_counts),
            "journey_stage_counts": dict(stage_counts),
            "draft_intervention_count": len(interventions),
            "interventions_artifact": INTERVENTIONS_PATH,
            "peer_goal_packet_count": len(peers["signals"]),
            "peer_goal_signals": peers["signals"],
        },
        recommendation="Instrument the first-value journey, fix product friction before adding messages, and test one customer-visible next-step intervention with strict frequency and trust guardrails.",
        confidence="low" if synthetic or len(rows) < 20 else "medium",
        risks=["Lifecycle messaging can become manipulative or spammy.", "Progress language can imply unsupported learning outcomes.", "Sensitive cases require human escalation."],
        requested_approval=["Approve customer-facing copy, frequency caps, support escalation rules, and cohort success metrics before sending."],
        outputs=["journey friction map", "draft intervention queue", "voice-of-customer themes"],
        next_check="After complete activation and four-week retention cohorts are available.",
    )
    return {**persist_packet(context, packet), "interventions_artifact": INTERVENTIONS_PATH}


def _publish_lifecycle_packet(context: dict[str, Any]) -> dict[str, Any]:
    inputs = normalized_inputs(context)
    business_name = str(inputs["business_name"])
    rows, source, synthetic = _dataset(context)
    themes = Counter(str(row.get("theme") or "unknown") for row in rows)
    peers = peer_signals(context)
    packet = build_packet(
        context,
        stage="publish_customer_lifecycle_packet",
        objective="Publish an evidence-backed customer lifecycle and product-intelligence packet without contacting customers.",
        trigger="Journey diagnosis and draft intervention checks are complete.",
        sources=[source],
        observed_facts=[f"The lifecycle diagnosis covers {len(rows)} feedback records and {len(themes)} themes."],
        assumptions=["The feedback set must be joined to de-identified behavioral cohorts before estimating impact."],
        analysis={
            "theme_counts": dict(themes),
            "interventions_artifact": INTERVENTIONS_PATH,
            "send_authorized": False,
            "peer_goal_packet_count": len(peers["signals"]),
            "peer_goal_signals": peers["signals"],
        },
        recommendation="Prioritize time-to-first-value and customer-visible next steps; share aggregate segment and objection evidence with Growth rather than raw customer records.",
        confidence="low" if synthetic or len(rows) < 20 else "medium",
        risks=["Small feedback samples can overrepresent vocal users.", "Automated messages can damage trust."],
        requested_approval=["Founder approves any lifecycle experiment or communication; sensitive support cases stay human-managed."],
        outputs=["Customer Lifecycle decision packet", "aggregate product intelligence"],
        next_check="At the weekly cohort review and after each approved intervention test.",
        publication_state="final",
    )
    persisted = persist_packet(context, packet)
    final = write_final_artifact(
        context,
        packet,
        artifact_type="customer_lifecycle_operating_brief",
        executive_summary=f"The GTM Assistant translated {business_name}'s de-identified feedback into journey friction, draft interventions, and product priorities while keeping every customer communication behind approval.",
        evidence={"feedback_record_count": len(rows), "theme_counts": dict(themes), "interventions_artifact": INTERVENTIONS_PATH, "send_authorized": False},
        next_steps=[
            "Join feedback themes to de-identified activation and retention cohorts.",
            "Fix technical or product friction before adding communications.",
            "Human-review one minimal customer-facing intervention and its frequency cap.",
            "Share aggregate retained-segment and objection evidence with Growth through MCP.",
        ],
        data_status="synthetic_demo" if synthetic else "user_supplied",
        role_contribution="Turn customer behavior and feedback into faster first value, stronger retention, better product priorities, and trustworthy lifecycle experiments.",
        north_star_question="Which product or lifecycle change helps the right customers reach and repeat meaningful value without pressure or unsupported claims?",
        role_scorecard=[
            {"metric": "feedback_records_reviewed", "current": len(rows), "target": "representative, de-identified, cohort-linked evidence", "decision_use": "Shows evidence coverage without overstating prevalence."},
            {"metric": "journey_themes", "current": len(themes), "target": "owned top frictions with measurable product responses", "decision_use": "Focuses work on the largest observable barriers."},
            {"metric": "time_to_first_value", "current": "not_measured", "target": "defined and decreasing", "decision_use": "Connects onboarding work to activation."},
            {"metric": "retained_customer_rate", "current": "not_measured", "target": "improving by cohort", "decision_use": "Supplies Finance and Growth with durable value evidence."},
            {"metric": "approved_intervention_effect", "current": "not_measured", "target": "incremental value without trust, frequency, or support regressions", "decision_use": "Separates helpful intervention from more messaging."},
        ],
        founder_decisions=[
            {"decision": "Choose the first-value event and retention window", "why_now": "Lifecycle performance cannot be improved or priced without a shared definition of customer value."},
            {"decision": "Prioritize one product fix before one message test", "why_now": "Communications should not disguise technical or product friction."},
            {"decision": "Approve the intervention cohort, copy, frequency cap, and stop rule", "why_now": "Every customer-facing experiment remains a human decision."},
        ],
        cross_functional_handoffs=[
            {"to": "business_finance_controller", "provides": "activation, retention, churn, support-load, and cancellation evidence", "needs_from": "retained-value and churn targets plus experiment cash constraints"},
            {"to": "growth_partnerships_lead", "provides": "retained segments, objections, customer language, and reasons for churn", "needs_from": "promise made by channel, audience source, and acquisition context"},
            {"to": "content_studio_director", "provides": "content gaps, continuation needs, and retained-use patterns", "needs_from": "approved assets, package metadata, and release timing"},
            {"to": "learning_quality_safety_director", "provides": "confusion, complaints, sensitive cases, and observed value gaps", "needs_from": "safe progress language, claim boundaries, and escalation triggers"},
        ],
        ninety_day_plan=[
            {"days": "0-30", "outcome": "Define first value, map the supplied feedback to journey stages, and instrument one complete activation cohort."},
            {"days": "31-60", "outcome": "Fix the highest-confidence product friction, then run one approved minimal intervention with a holdout or clear baseline."},
            {"days": "61-90", "outcome": "Recommend product, content, channel, and lifecycle priorities using retained behavior, customer trust, support load, and Finance thresholds."},
        ],
        peer_context=peers,
    )
    return {**persisted, **final}


def _intervention(theme: str, count: int, *, business_name: str) -> dict[str, Any]:
    draft = normalize_structured_draft(
        {
            "subject": f"A simple next step in your {business_name} routine",
            "preview_text": "A customer-directed draft that helps continue a useful routine without pressure.",
            "body_sections": [
                {"title": "What we noticed", "body": f"Some customers reported friction related to {theme.replace('_', ' ')}."},
                {"title": "A small next step", "body": "The product should offer one relevant continuation and make the practiced skill clear to the adult account holder."},
            ],
            "cta_label": "Review the next activity",
            "footer": "Draft only — do not send without approval, relevance checks, and frequency limits.",
        }
    )
    return {
        "theme": theme,
        "feedback_record_count": count,
        "intervention_order": ["verify no product defect", "offer one relevant next step", "ask one focused question if needed"],
        "draft": draft,
        "draft_review": review_email_quality(draft=draft, forbidden_phrases=("guaranteed", "therapy", "diagnose")),
        "send_authorized": False,
    }
