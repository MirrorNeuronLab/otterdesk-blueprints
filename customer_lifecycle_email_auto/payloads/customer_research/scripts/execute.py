#!/usr/bin/env python3
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _synaptic_runtime.core import (
    completion_json,
    db_connect,
    load_input_manifest,
    load_input_plan,
    load_knowledge_section,
    log_agent,
    latest_sent_draft,
    pending_ready_draft,
    read_business_context,
    recent_activities,
)
from _synaptic_skills.marketing_email import (
    build_customer_brief,
    infer_audience_segment,
    parse_source_payload,
)


AGENT_ID = "customer_research_agent"
logger = logging.getLogger("mn.blueprint.business_email.customer_research")


def has_thread_reply_context(plan: dict) -> bool:
    reply_context = plan.get("reply_context") or {}
    if not isinstance(reply_context, dict):
        return False
    for key in ("thread_message_id", "in_reply_to_message_id", "message_id"):
        if str(reply_context.get(key) or "").strip():
            return True
    references = reply_context.get("references_message_ids")
    return isinstance(references, list) and any(str(ref or "").strip() for ref in references)


def should_select_reply_followup(
    *,
    plan: dict,
    activities: list[dict],
    past_campaigns: list[str],
) -> bool:
    if "reply_followup" in past_campaigns or not has_thread_reply_context(plan):
        return False
    return any(
        str(activity.get("summary") or "").startswith("Customer replied:")
        for activity in activities
    )


def fallback_brief(plan: dict, activities: list[dict]) -> dict:
    return build_customer_brief(
        plan=plan,
        activities=activities,
        segments=load_knowledge_section("segments"),
        playbooks=load_knowledge_section("campaign_playbooks"),
        offers_catalog=load_knowledge_section("offers_catalog"),
        recent_memory=parse_source_payload(
            (latest_sent_draft(plan["customer"]["customer_id"]) or {}).get(
                "source_payload_json"
            )
        ),
    )


def main() -> None:
    plan = load_input_plan()
    customer = plan["customer"]
    runtime_job_id = plan.get("runtime_job_id")

    existing_draft = pending_ready_draft(customer["customer_id"])
    if existing_draft is not None:
        plan["existing_draft"] = existing_draft
        log_agent(runtime_job_id, AGENT_ID, "Skipped research because a ready draft already exists.")
        print(json.dumps(plan))
        return

    activities = recent_activities(customer["customer_id"], limit=5)
    input_manifest = load_input_manifest()
    context_text = read_business_context()
    segments = load_knowledge_section("segments")
    playbooks = load_knowledge_section("campaign_playbooks")
    offers_catalog = load_knowledge_section("offers_catalog")
    audience_segment = plan.get("audience_segment") or infer_audience_segment(customer, segments)
    plan["audience_segment"] = audience_segment

    parent_sequence = [
        "parent_awareness",
        "parent_education",
        "parent_activation",
        "parent_social_proof",
        "parent_use_case",
        "parent_reminder",
        "parent_expansion",
    ]
    teacher_sequence = [
        "teacher_awareness",
        "teacher_education",
        "teacher_activation",
        "teacher_social_proof",
        "teacher_use_case",
        "teacher_reminder",
        "teacher_expansion",
    ]
    creator_sequence = [
        "creator_awareness",
        "creator_education",
        "creator_activation",
        "creator_social_proof",
        "creator_use_case",
        "creator_reminder",
        "creator_expansion",
    ]
    if audience_segment == "teachers":
        sequence = teacher_sequence
    elif audience_segment == "creators_educators":
        sequence = creator_sequence
    else:
        sequence = parent_sequence
    
    past_campaigns = []
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT source_payload_json FROM email_drafts WHERE customer_id = ? AND status = 'sent' ORDER BY sent_at ASC",
            (customer["customer_id"],)
        ).fetchall()
        for row in rows:
            try:
                sp = json.loads(row["source_payload_json"])
                if "campaign_type" in sp:
                    past_campaigns.append(sp["campaign_type"])
            except:
                pass

    next_campaign = sequence[0]
    for camp in sequence:
        if camp not in past_campaigns:
            next_campaign = camp
            break

    if should_select_reply_followup(
        plan=plan,
        activities=activities,
        past_campaigns=past_campaigns,
    ):
        next_campaign = "reply_followup"
        
    plan["campaign_type"] = next_campaign
    plan["goal"] = playbooks.get(next_campaign, {}).get("goal", "")
    plan["success_metric"] = playbooks.get(next_campaign, {}).get("success_metric", "")

    logger.info("Evaluated customer %s", customer["name"])
    logger.info("Selected campaign step: %s", next_campaign)

    latest_source = parse_source_payload(
        (latest_sent_draft(customer["customer_id"]) or {}).get("source_payload_json")
    )

    system_prompt = (
        "You are the customer research agent in a multi-agent email marketing system. "
        "Return compact JSON only. Build a strategic brief for one high-quality email in a 30-day, multi-step campaign. "
        "Treat Bibblio as an Emotional Learning Content platform, not a bookstore. "
        "Choose an angle for the selected audience and phase; never reuse a generic parent message for a teacher or creator. "
        "Every brief must include at least two messaging triggers: emotional pain, identity, outcome, or ease. "
        "Required keys: persona, customer_angle, job_to_be_done, pain_point, recommended_offer, "
        "offer_reason, proof_points, objection_to_address, primary_cta, secondary_cta, angle_to_avoid, "
        "recommended_template, activity_summary, tone. "
        "If campaign_type is reply_followup, write the brief as if a helpful human is replying in-thread."
    )
    user_prompt = json.dumps(
        {
            "business_context": context_text,
            "positioning": input_manifest.get("positioning", {}),
            "funnel_strategy": input_manifest.get("funnel_strategy", {}),
            "messaging_dna": input_manifest.get("messaging_dna", {}),
            "strategy": {
                "campaign_type": plan.get("campaign_type"),
                "audience_segment": plan.get("audience_segment"),
                "primary_offer": plan.get("primary_offer"),
                "why_now": plan.get("why_now"),
                "goal": plan.get("goal"),
                "success_metric": plan.get("success_metric"),
            },
            "customer": customer,
            "recent_activities": activities,
            "reply_context": plan.get("reply_context", {}),
            "audience_segment_profile": segments.get(
                plan.get("audience_segment", "general_audience"), {}
            ),
            "campaign_playbook": playbooks.get(plan.get("campaign_type", "product_spotlight"), {}),
            "offers_catalog": offers_catalog,
            "recent_email_memory": latest_source,
            "task": "Create a concise but strategy-rich customer brief for a personalized marketing email.",
        },
        indent=2,
    )

    deterministic_brief = fallback_brief(plan, activities)
    brief = completion_json(system_prompt, user_prompt, profile="secondary") or deterministic_brief
    for key in (
        "campaign_phase",
        "subject_angle",
        "recommended_template",
        "primary_cta",
        "secondary_cta",
    ):
        if deterministic_brief.get(key):
            brief[key] = brief.get(key) or deterministic_brief[key]
    if plan.get("campaign_type", "").startswith(("teacher_", "creator_")):
        for key in ("recommended_offer", "offer_reason", "proof_points", "story_prompt_example"):
            if deterministic_brief.get(key):
                brief[key] = deterministic_brief[key]
    plan["customer_brief"] = brief
    plan["recent_activities"] = activities
    log_agent(
        runtime_job_id,
        AGENT_ID,
        "Prepared customer research brief.",
        details={
            "activity_count": len(activities),
            "campaign_type": plan.get("campaign_type"),
            "recommended_template": brief.get("recommended_template"),
        },
    )
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
