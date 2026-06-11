#!/usr/bin/env python3
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


AGENT_ID = "lifecycle_copywriter_agent"


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
        "You are a senior lifecycle email copywriter for a professional 30-day email marketing campaign. Return JSON only. "
        "Required keys: subject_candidates, preview_text, eyebrow, headline, body_sections, cta_label, cta_url_slug, footer_variant, secondary_text, signoff. "
        "Write one strong email for one audience, one campaign phase, one offer, and one primary CTA. "
        "Position Bibblio as an Emotional Learning Content platform where teachers, parents, and creators co-create emotional learning stories for kids; do not position it as a bookstore. "
        "Use the recipient's audience segment: teachers need classroom practicality, parents need emotional reassurance, and creators need purpose plus opportunity. "
        "Every email must use at least two of these triggers: emotional pain, identity, outcome, ease. "
        "Lead with the human problem, then reframe through story-based emotional learning, then make the next action feel concrete and low-friction. "
        "Use short paragraphs, clear benefits, specific proof, and a professional warm tone. Avoid generic newsletters, feature lists, hype, and clinical claims. "
        "If campaign_type is reply_followup, write like a real human replying personally: short, warm, specific, conversational, and not like a newsletter. "
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
    log_agent(runtime_job_id, AGENT_ID, "Prepared lifecycle copy.")
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
