#!/usr/bin/env python3.11
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _synaptic_runtime.core import (
    completion_json,
    load_input_manifest,
    load_knowledge_section,
    load_input_plan,
    log_agent,
    read_business_context,
)
from _synaptic_skills.marketing_email import normalize_structured_draft


AGENT_ID = "outreach_copywriter_agent"


def fallback_draft(plan: dict) -> dict:
    return normalize_structured_draft(
        {},
        plan=plan,
        brand=load_knowledge_section("brand"),
    )


def main() -> None:
    plan = load_input_plan()
    runtime_job_id = plan.get("runtime_job_id")

    if plan.get("existing_draft"):
        log_agent(runtime_job_id, AGENT_ID, "Skipped copywriting because a ready draft already exists.")
        print(json.dumps(plan))
        return
    input_manifest = load_input_manifest()

    system_prompt = (
        "You are a senior B2B sales email copywriter in a GTM AI workflow. Return JSON only. "
        "Required keys: subject_candidates, preview_text, eyebrow, headline, body_sections, cta_label, cta_url_slug, footer_variant, secondary_text, signoff. "
        "Write one strong email for one target account, one likely pain, one offer, and one primary CTA. "
        "Position GTM AI Workflow as a learning loop from market signal to outreach, response, CRM state, product insight, and better positioning. "
        "Every email must use at least two triggers: market signal, likely pain, business outcome, ease. "
        "Lead with the account-specific signal, then the likely GTM pain, then make the next action concrete and low-friction. "
        "Use short paragraphs, clear benefits, specific proof, and a professional tone. Avoid generic newsletters, feature lists, hype, and unverifiable claims. "
        "If campaign_type is response_followup or reply_followup, write like a real human replying personally: short, warm, specific, conversational, and not like a newsletter. "
        "body_sections must be an array of plain paragraph strings, not objects."
    )
    user_prompt = json.dumps(
        {
            "business_context": read_business_context(),
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
            "customer": plan["customer"],
            "customer_brief": plan.get("customer_brief", {}),
            "recent_activities": plan.get("recent_activities", []),
            "reply_context": plan.get("reply_context", {}),
            "brand": load_knowledge_section("brand"),
        },
        indent=2,
    )
    plan["draft"] = normalize_structured_draft(
        completion_json(system_prompt, user_prompt, profile="primary"),
        plan=plan,
        brand=load_knowledge_section("brand"),
    )
    if not plan["draft"]:
        plan["draft"] = fallback_draft(plan)
    log_agent(runtime_job_id, AGENT_ID, "Prepared personalized GTM outreach copy.")
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
