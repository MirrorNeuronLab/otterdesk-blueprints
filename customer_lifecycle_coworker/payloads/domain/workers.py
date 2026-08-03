from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from mn_marketing_email_skill import normalize_structured_draft, review_email_quality
from mn_sdk.blueprint_support.workflow_state import write_json

from .collaboration import build_packet, peer_signals, persist_packet, write_final_artifact
from .inputs import csv_rows, resolve_input_file, source_descriptor


INTERVENTIONS_PATH = "draft_parent_interventions.json"


def run_parent_lifecycle_director(context: dict[str, Any], *, step_id: str, **_: Any) -> dict[str, Any]:
    if step_id == "diagnose_parent_journey":
        return _diagnose_parent_journey(context)
    if step_id == "publish_parent_lifecycle_packet":
        return _publish_lifecycle_packet(context)
    raise ValueError(f"Parent Lifecycle co-worker does not own step {step_id!r}")


def _dataset(context: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any], bool]:
    path = resolve_input_file(context, "parent_feedback_file", "parent_feedback.csv")
    rows = csv_rows(path)
    synthetic = any(str(row.get("data_status") or "").lower() == "synthetic_demo" for row in rows)
    return rows, source_descriptor(path, synthetic=synthetic), synthetic


def _diagnose_parent_journey(context: dict[str, Any]) -> dict[str, Any]:
    rows, source, synthetic = _dataset(context)
    theme_counts = Counter(str(row.get("theme") or "unknown") for row in rows)
    stage_counts = Counter(str(row.get("journey_stage") or "unknown") for row in rows)
    interventions = [_intervention(theme, count) for theme, count in theme_counts.most_common(5)]
    write_json(
        Path(context["run_dir"]) / INTERVENTIONS_PATH,
        {
            "schema_version": "mn.bibblio.parent_interventions.v1",
            "mode": "draft_only",
            "send_authorized": False,
            "interventions": interventions,
        },
    )
    peers = peer_signals(context)
    packet = build_packet(
        context,
        stage="diagnose_parent_journey",
        objective="Identify the activation, retention, support, and value-proof friction that prevents families from reaching sustained value.",
        trigger="De-identified parent feedback or lifecycle observations are supplied.",
        sources=[source],
        observed_facts=[
            f"The supplied feedback set contains {len(rows)} records.",
            f"Theme counts are {dict(theme_counts)}.",
            f"Journey-stage counts are {dict(stage_counts)}.",
        ],
        assumptions=["Frequency in a small or synthetic feedback set is not population prevalence.", "Draft interventions must be tested against behavioral cohorts before automation."],
        analysis={
            "theme_counts": dict(theme_counts),
            "journey_stage_counts": dict(stage_counts),
            "draft_intervention_count": len(interventions),
            "interventions_artifact": INTERVENTIONS_PATH,
            "peer_goal_packet_count": len(peers["signals"]),
            "peer_goal_signals": peers["signals"],
        },
        recommendation="Instrument the first-value journey, fix product friction before adding messages, and test one parent-visible next-step intervention with strict frequency and trust guardrails.",
        confidence="low" if synthetic or len(rows) < 20 else "medium",
        risks=["Lifecycle messaging can become manipulative or spammy.", "Progress language can imply unsupported learning outcomes.", "Sensitive cases require human escalation."],
        requested_approval=["Approve parent-facing copy, frequency caps, support escalation rules, and cohort success metrics before sending."],
        outputs=["journey friction map", "draft intervention queue", "voice-of-parent themes"],
        next_check="After complete activation and four-week retention cohorts are available.",
    )
    return {**persist_packet(context, packet), "interventions_artifact": INTERVENTIONS_PATH}


def _publish_lifecycle_packet(context: dict[str, Any]) -> dict[str, Any]:
    rows, source, synthetic = _dataset(context)
    themes = Counter(str(row.get("theme") or "unknown") for row in rows)
    packet = build_packet(
        context,
        stage="publish_parent_lifecycle_packet",
        objective="Publish an evidence-backed parent lifecycle and product-intelligence packet without contacting families.",
        trigger="Journey diagnosis and draft intervention checks are complete.",
        sources=[source],
        observed_facts=[f"The lifecycle diagnosis covers {len(rows)} feedback records and {len(themes)} themes."],
        assumptions=["The feedback set must be joined to de-identified behavioral cohorts before estimating impact."],
        analysis={"theme_counts": dict(themes), "interventions_artifact": INTERVENTIONS_PATH, "send_authorized": False},
        recommendation="Prioritize time-to-first-value and parent-visible next steps; share aggregate segment and objection evidence with GTM rather than raw family records.",
        confidence="low" if synthetic or len(rows) < 20 else "medium",
        risks=["Small feedback samples can overrepresent vocal users.", "Automated messages can damage trust."],
        requested_approval=["Founder approves any lifecycle experiment or communication; sensitive support cases stay human-managed."],
        outputs=["Parent Lifecycle decision packet", "aggregate product intelligence"],
        next_check="At the weekly cohort review and after each approved intervention test.",
        publication_state="final",
    )
    persisted = persist_packet(context, packet)
    final = write_final_artifact(
        context,
        packet,
        artifact_type="bibblio_parent_lifecycle_packet",
        executive_summary="The Parent Lifecycle co-worker translated de-identified feedback into journey friction, draft interventions, and product priorities while keeping every parent communication behind approval.",
        evidence={"feedback_record_count": len(rows), "theme_counts": dict(themes), "interventions_artifact": INTERVENTIONS_PATH, "send_authorized": False},
        next_steps=[
            "Join feedback themes to de-identified activation and retention cohorts.",
            "Fix technical or product friction before adding communications.",
            "Human-review one minimal parent-facing intervention and its frequency cap.",
            "Share aggregate retained-segment and objection evidence with GTM through MCP.",
        ],
        data_status="synthetic_demo" if synthetic else "user_supplied",
    )
    return {**persisted, **final}


def _intervention(theme: str, count: int) -> dict[str, Any]:
    draft = normalize_structured_draft(
        {
            "subject": "A simple next step in your Bibblio routine",
            "preview_text": "A parent-directed draft that helps continue a learning routine without pressure.",
            "body_sections": [
                {"title": "What we noticed", "body": f"Some parents reported friction related to {theme.replace('_', ' ')}."},
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
