from __future__ import annotations

import ast
import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


GENERIC_MARKETING_PHRASES = (
    "ai children book creator",
    "ai book maker",
    "bookstore",
    "content library",
    "generic product",
    "use credits",
    "create a book",
)


def _keyword_matches_text(keyword: str, text: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text.lower()))


def infer_audience_segment(
    customer: dict[str, Any], segments: dict[str, Any] | None = None
) -> str:
    explicit = (
        customer.get("segment")
        or customer.get("inferred_attributes", {}).get("segment")
        or customer.get("factual_attributes", {}).get("segment")
    )
    if explicit:
        return str(explicit)

    tags = [str(tag).lower() for tag in customer.get("tags", [])]
    job_title = str(customer.get("job_title") or customer.get("title") or "").lower()
    segments = dict(segments or {})
    for segment_id, config in segments.items():
        keywords = [str(item).lower() for item in config.get("keywords", [])]
        if any(_keyword_matches_text(keyword, job_title) for keyword in keywords):
            return str(segment_id)
        if any(_keyword_matches_text(keyword, tag) for tag in tags for keyword in keywords):
            return str(segment_id)

    if any(token in tags for token in ["gift", "gift-shopper", "keepsake"]):
        return "gift_memory_shoppers"
    if "customer" in job_title or any("customer" in tag for tag in tags):
        return "existing_customers"
    if any(token in job_title for token in ["parent", "mom", "mother", "dad", "father"]):
        return "new_parents"
    if any(token in tags for token in ["parent", "mom", "dad", "caregiver"]):
        return "new_parents"
    if any(token in job_title for token in ["buyer", "owner", "manager"]) or any(
        token in tag for tag in tags for token in ["buyer", "intent", "decision-maker"]
    ):
        return "engaged_buyers"
    return "general_audience"


def infer_campaign_type(recent_activities: list[dict[str, Any]]) -> str:
    summaries = " ".join(
        str(activity.get("summary", "")).lower() for activity in recent_activities
    )
    if any(
        token in summaries
        for token in [
            "received inbound email reply",
            "replied to email",
            "inbound email",
            "customer replied",
        ]
    ):
        return "reply_followup"
    if any(
        token in summaries
        for token in [
            "shared referral",
            "referral link",
            "successful referral",
            "invite link",
        ]
    ):
        return "referral_invite"
    if any(
        token in summaries
        for token in [
            "purchased credits",
            "low remaining credits",
            "credits balance",
            "checkout for credits",
        ]
    ):
        return "credit_purchase_nudge"
    if any(
        token in summaries
        for token in [
            "downloaded pdf",
            "downloaded book",
            "story ready",
            "created first story",
            "completed book",
        ]
    ):
        return "download_conversion"
    if any(
        token in summaries
        for token in [
            "started a book",
            "draft abandoned",
            "started but did not",
            "unfinished draft",
            "resume editing",
        ]
    ):
        return "draft_recovery"
    if any(
        token in summaries
        for token in [
            "signed up",
            "joined bibblio",
            "no story started",
            "inactive for 21",
            "inactive for 30",
            "has not returned",
        ]
    ):
        return "first_story_activation"
    if any(
        token in summaries
        for token in [
            "created 2 stories",
            "created another story",
            "repeat creator",
            "started second story",
        ]
    ):
        return "next_story_idea"
    if any(
        token in summaries for token in ["clicked", "newsletter", "program", "workflow", "guide"]
    ):
        return "program_reminder"
    if any(token in summaries for token in ["cart", "abandoned", "trial", "pricing"]):
        return "interest_followup"
    return "product_spotlight"


def _quoted_titles(recent_activities: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for activity in recent_activities:
        summary = str(activity.get("summary", ""))
        titles.extend(re.findall(r"'([^']+)'", summary))
    return titles


def _normalize_slug(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "discover"


def _find_offer_by_title(
    offers: list[dict[str, Any]], title: str | None
) -> dict[str, Any] | None:
    if not title:
        return None
    title_lower = title.lower()
    for offer in offers:
        name = str(offer.get("title") or offer.get("name") or "").lower()
        if name == title_lower:
            return offer
    return None


def choose_primary_offer(
    customer: dict[str, Any],
    recent_activities: list[dict[str, Any]],
    offers_catalog: dict[str, Any],
    campaign_type: str,
) -> dict[str, Any]:
    offers = list(offers_catalog.get("offers", []))
    preferred_topics = [
        str(item)
        for item in customer.get("inferred_attributes", {}).get("preferred_topics", [])
    ]
    tags = [str(tag).lower() for tag in customer.get("tags", [])]
    summaries = " ".join(
        str(activity.get("summary", "")).lower() for activity in recent_activities
    )

    def find_offer_by_keywords(*wanted_keywords: str) -> dict[str, Any] | None:
        wanted = {keyword.lower() for keyword in wanted_keywords}
        for offer in offers:
            haystack = {
                str(offer.get("title") or offer.get("name") or "").lower(),
                str(offer.get("id", "")).lower(),
                str(offer.get("url_slug", "")).lower(),
            }
            haystack.update(str(keyword).lower() for keyword in offer.get("keywords", []))
            if any(any(wanted_keyword in item for item in haystack) for wanted_keyword in wanted):
                return offer
        return None

    if campaign_type == "credit_purchase_nudge":
        offer = find_offer_by_keywords("credit", "credits", "pack")
        if offer:
            return offer

    if campaign_type.startswith("teacher_"):
        offer = find_offer_by_keywords("sel") or find_offer_by_keywords(
            "classroom", "teacher"
        )
        if offer:
            return offer

    if campaign_type.startswith("creator_"):
        offer = find_offer_by_keywords("creator", "emotional learning", "publish")
        if offer:
            return offer

    if campaign_type == "referral_invite":
        offer = find_offer_by_keywords("referral", "invite", "share")
        if offer:
            return offer

    if campaign_type == "reply_followup":
        titles = _quoted_titles(recent_activities)
        offer = _find_offer_by_title(offers, titles[-1] if titles else None)
        if offer:
            return offer

    if campaign_type == "interest_followup":
        titles = _quoted_titles(recent_activities)
        offer = _find_offer_by_title(offers, titles[-1] if titles else None)
        if offer:
            return offer

    if campaign_type == "download_conversion":
        offer = find_offer_by_keywords("keepsake", "download", "gift", "printable")
        if offer:
            return offer

    if campaign_type in {"draft_recovery", "first_story_activation", "next_story_idea"}:
        for keyword in preferred_topics:
            offer = find_offer_by_keywords(keyword)
            if offer:
                return offer
        if any(tag in {"gift", "gift-shopper", "keepsake"} for tag in tags):
            offer = find_offer_by_keywords("keepsake", "gift")
            if offer:
                return offer
        for keyword in ["bedtime", "feelings", "bravery", "friendship", "school"]:
            if keyword in summaries:
                offer = find_offer_by_keywords(keyword)
                if offer:
                    return offer

    wanted = {topic.lower() for topic in preferred_topics}
    for offer in offers:
        offer_keywords = {
            str(keyword).lower() for keyword in offer.get("keywords", [])
        }
        if wanted & offer_keywords:
            return offer

    return offers[0] if offers else {}


def build_marketing_strategy(
    customer: dict[str, Any],
    recent_activities: list[dict[str, Any]],
    offers_catalog: dict[str, Any],
    playbooks: dict[str, Any],
    segments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audience_segment = infer_audience_segment(customer, segments)
    campaign_type = infer_campaign_type(recent_activities)
    playbook = dict(playbooks.get(campaign_type, {}))
    offer = choose_primary_offer(customer, recent_activities, offers_catalog, campaign_type)
    offer_name = str(offer.get("title") or offer.get("name") or "A practical next step")
    why_now = str(
        playbook.get("why_now")
        or "Recent activity suggests this is a timely and relevant follow-up."
    )
    goal = str(playbook.get("goal") or "Drive a qualified click")
    success_metric = str(playbook.get("success_metric") or "Primary CTA click")
    return {
        "campaign_type": campaign_type,
        "audience_segment": audience_segment,
        "primary_offer": offer_name,
        "primary_offer_id": offer.get("id", _normalize_slug(offer_name)),
        "why_now": why_now,
        "goal": goal,
        "success_metric": success_metric,
    }


def build_customer_brief(
    *,
    plan: dict[str, Any],
    activities: list[dict[str, Any]],
    segments: dict[str, Any],
    playbooks: dict[str, Any],
    offers_catalog: dict[str, Any],
    recent_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    customer = plan["customer"]
    strategy = {
        "campaign_type": plan.get("campaign_type", "product_spotlight"),
        "audience_segment": plan.get(
            "audience_segment", infer_audience_segment(customer, segments)
        ),
        "primary_offer": plan.get("primary_offer", "A practical next step"),
    }
    segment = dict(segments.get(strategy["audience_segment"], {}))
    playbook = dict(playbooks.get(strategy["campaign_type"], {}))
    offer = choose_primary_offer(
        customer, activities, offers_catalog, strategy["campaign_type"]
    )
    offer_name = str(offer.get("title") or offer.get("name") or strategy["primary_offer"])
    proof_points = list(offer.get("benefit_bullets", []))[:2]
    if not proof_points:
        proof_points = [
            "It connects the customer's recent interest to one clear next step.",
            "It keeps the message specific and easier to act on.",
        ]
    recent_template = (
        recent_memory.get("design", {}).get("template")
        if isinstance(recent_memory, dict)
        else None
    )
    return {
        "persona": segment.get("label", "General audience"),
        "customer_angle": (
            str(customer.get("profile") or "").strip()
            or f"{customer.get('name')} is a {customer.get('job_title') or customer.get('title') or 'customer'}"
            f" who may benefit from a clearer next step."
        ),
        "job_to_be_done": segment.get(
            "job_to_be_done",
            "Understand the value quickly and decide on a useful next step.",
        ),
        "pain_point": segment.get(
            "pain_point",
            "Needs a relevant recommendation without extra complexity or noise.",
        ),
        "recommended_offer": offer_name,
        "offer_reason": playbook.get(
            "offer_reason",
            "It matches the customer's recent interest and gives them one simple decision to make.",
        ),
        "campaign_phase": playbook.get("phase", ""),
        "subject_angle": playbook.get("subject_angle", ""),
        "messaging_triggers": playbook.get(
            "messaging_triggers",
            ["emotional pain", "identity", "outcome", "ease"],
        )[:4],
        "proof_points": proof_points,
        "story_prompt_example": offer.get(
            "story_prompt_example",
            "A gentle story that helps a child move through a real moment with more confidence.",
        ),
        "objection_to_address": segment.get(
            "objection_to_address",
            "Why is this relevant right now, and why is it worth the click?",
        ),
        "primary_cta": {
            "label": playbook.get("primary_cta_label", "Explore the offer"),
            "url_slug": offer.get("url_slug", playbook.get("default_url_slug", "discover")),
        },
        "secondary_cta": {
            "label": playbook.get("secondary_cta_label", "See related options"),
            "url_slug": playbook.get("secondary_url_slug", "solutions"),
        },
        "angle_to_avoid": recent_template or playbook.get(
            "angle_to_avoid",
            "Avoid repeating the exact last hook or sounding generic.",
        ),
        "recommended_template": playbook.get("recommended_template", "product_spotlight"),
        "activity_summary": [item.get("summary", "") for item in activities],
        "tone": segment.get("tone", "clear, practical, and useful"),
    }


def choose_best_subject(
    subject_candidates: list[str],
    *,
    customer: dict[str, Any],
    primary_offer: str,
) -> str:
    first_name = (customer.get("name") or "there").split()[0]
    if first_name.lower().rstrip(".") in {"mr", "mrs", "ms", "miss", "dr"}:
        first_name = str(customer.get("name") or first_name).strip()

    def score(candidate: str) -> tuple[int, int]:
        text = candidate.strip()
        lower = text.lower()
        score_value = 0
        if 28 <= len(text) <= 58:
            score_value += 4
        elif 20 <= len(text) <= 68:
            score_value += 2
        if first_name.lower() in lower:
            score_value += 2
        if any(word in lower for word in primary_offer.lower().split()[:2]):
            score_value += 2
        if "!" not in text:
            score_value += 1
        if len(text.split()) <= 10:
            score_value += 1
        return score_value, -len(text)

    filtered = [
        candidate.strip()
        for candidate in subject_candidates
        if candidate and candidate.strip()
    ]
    if not filtered:
        return f"{first_name}, a useful next step worth a closer look"
    return sorted(filtered, key=score, reverse=True)[0]


def _coerce_body_section(item: Any) -> str:
    if isinstance(item, str):
        stripped = item.strip()
        if stripped and stripped[0] in "[{":
            try:
                parsed = ast.literal_eval(stripped)
            except (SyntaxError, ValueError):
                parsed = None
            if parsed is not None:
                return _coerce_body_section(parsed)
        return stripped
    if isinstance(item, dict):
        for key in ("content", "text", "body", "copy"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                parts = [str(part).strip() for part in value if str(part).strip()]
                if parts:
                    return "\n\n".join(parts)
        return ""
    if isinstance(item, list):
        parts = [_coerce_body_section(part) for part in item]
        return "\n\n".join(part for part in parts if part)
    return str(item).strip()


def normalize_body_sections(items: list[Any] | None) -> list[str]:
    normalized = [_coerce_body_section(item) for item in (items or [])]
    return [section for section in normalized if section]


def compose_text_body(draft: dict[str, Any], cta_url: str | None = None) -> str:
    sections = normalize_body_sections(draft.get("body_sections", []))
    closing_lines = []
    if draft.get("cta_label") and cta_url:
        closing_lines.append(f"{draft['cta_label']}: {cta_url}")
    elif draft.get("cta_label"):
        closing_lines.append(str(draft["cta_label"]))
    signoff = str(draft.get("signoff", "")).strip()
    if signoff:
        closing_lines.append(signoff)
    return "\n\n".join(sections + closing_lines).strip()


def normalize_structured_draft(
    raw: dict[str, Any] | None,
    *,
    plan: dict[str, Any],
    brand: dict[str, Any],
) -> dict[str, Any]:
    raw = dict(raw or {})
    customer = plan["customer"]
    brief = plan.get("customer_brief", {})
    strategy = {
        "campaign_type": plan.get("campaign_type", "product_spotlight"),
        "primary_offer": plan.get(
            "primary_offer", brief.get("recommended_offer", "A practical next step")
        ),
        "audience_segment": plan.get("audience_segment", "general_audience"),
    }
    first_name = (customer.get("name") or "there").split()[0]
    if first_name.lower().rstrip(".") in {"mr", "mrs", "ms", "miss", "dr"}:
        first_name = str(customer.get("name") or first_name).strip()
    offer = str(brief.get("recommended_offer") or strategy["primary_offer"])
    cta_meta = brief.get("primary_cta", {})
    proof_points = list(brief.get("proof_points", []))[:2]
    persona = str(brief.get("persona") or "")
    story_prompt_example = str(brief.get("story_prompt_example") or "").strip()
    reply_context = dict(plan.get("reply_context") or {})
    subject_candidates = list(raw.get("subject_candidates") or [])
    campaign_type = strategy["campaign_type"]
    is_sel_campaign = campaign_type.startswith(("parent_", "teacher_", "creator_"))
    subject_angle = str(brief.get("subject_angle") or "").strip()
    campaign_phase = str(brief.get("campaign_phase") or "").strip()
    if len(subject_candidates) < 2:
        if campaign_type == "reply_followup":
            subject_root = str(reply_context.get("subject") or f"Re: {offer}").strip()
            if subject_root and not subject_root.lower().startswith("re:"):
                subject_root = f"Re: {subject_root}"
            subject_candidates = [
                subject_root or "Re: Quick follow-up",
                f"Re: {first_name}, thanks for replying",
                "Re: Quick follow-up from Bibblio",
            ]
        elif is_sel_campaign:
            if campaign_type.startswith("teacher_"):
                subject_candidates = [
                    subject_angle or "Why students remember stories but forget lessons",
                    "A practical SEL story idea for your classroom",
                    "One classroom moment, one story-based check-in",
                ]
            elif campaign_type.startswith("creator_"):
                subject_candidates = [
                    subject_angle or "Turn real childhood struggles into meaningful stories",
                    "A clearer category for purposeful children’s stories",
                    "Create emotional learning content with real utility",
                ]
            else:
                subject_candidates = [
                    subject_angle or "What your child may not say out loud",
                    f"{first_name}, a story idea for this week’s child moment",
                    "A five-minute way into a bigger conversation",
                ]
        elif campaign_type in {
            "first_story_activation",
            "draft_recovery",
            "download_conversion",
            "credit_purchase_nudge",
            "next_story_idea",
            "referral_invite",
            "winback_parent_moment",
        }:
            subject_candidates = [
                f"{first_name}, a story idea for this moment",
                f"A gentle next step for {offer.lower()}",
                f"{offer} could help with this week’s challenge",
            ]
        else:
            subject_candidates = [
                f"{first_name}, a useful next step worth a closer look",
                "A practical recommendation for right now",
                f"{offer} could be a strong fit right now",
            ]
    preview_text = str(
        raw.get("preview_text")
        or (
            "A quick, personal follow-up to your reply."
            if campaign_type == "reply_followup"
            else (
                f"Turn a real emotional learning moment into a personalized story with {offer}."
                if is_sel_campaign
                or campaign_type
                in {
                    "first_story_activation",
                    "draft_recovery",
                    "download_conversion",
                    "credit_purchase_nudge",
                    "next_story_idea",
                    "referral_invite",
                    "winback_parent_moment",
                }
                else f"A practical recommendation inspired by your recent interest in {offer}."
            )
        )
    ).strip()
    headline = str(raw.get("headline") or subject_angle or offer).strip()
    eyebrow = str(
        raw.get("eyebrow") or campaign_phase.replace("_", " ").title() or plan.get("goal") or "A useful next step"
    ).strip()
    body_sections = normalize_body_sections(raw.get("body_sections") or [])
    if len(body_sections) < 2:
        if campaign_type == "reply_followup":
            sender_name = str(reply_context.get("from_name") or first_name).strip()
            inbound_summary = str(reply_context.get("text_body") or "").strip()
            if len(inbound_summary) > 220:
                inbound_summary = inbound_summary[:217].rstrip() + "..."
            body_sections = [
                f"Hi {sender_name}, thanks for your reply. I wanted to follow up personally and make this easy.",
                (
                    proof_points[0]
                    if proof_points
                    else str(
                        brief.get("offer_reason")
                        or "Based on what you shared, I think the most helpful next step is to keep things simple and relevant."
                    )
                ),
                (
                    f"You mentioned: \"{inbound_summary}\""
                    if inbound_summary
                    else story_prompt_example
                    or "If it helps, I can point you to the best next story idea or the fastest way to finish what you started."
                ),
            ]
        elif is_sel_campaign:
            if campaign_type.startswith("teacher_"):
                body_sections = [
                    f"Hi {first_name}, students often remember a story long after a lesson fades. That is why {offer} is built around classroom moments, not generic content.",
                    proof_points[0]
                    if proof_points
                    else "It gives you a practical way to approach friendship, anxiety, bullying, confidence, or belonging without adding a heavy new curriculum.",
                    story_prompt_example
                    or "Start with one five-minute check-in: choose a classroom challenge, turn it into a story, and let students discuss the choice the character makes next.",
                ]
            elif campaign_type.startswith("creator_"):
                body_sections = [
                    f"Hi {first_name}, emotional learning content is becoming its own category: stories that help children understand real struggles through narrative.",
                    proof_points[0]
                    if proof_points
                    else f"{offer} helps creators turn purpose into stories parents and teachers can actually use.",
                    story_prompt_example
                    or "Choose one theme, such as anxiety, friendship, bullying, confidence, or school transitions, and publish a story that gives children language for the moment.",
                ]
            else:
                body_sections = [
                    f"Hi {first_name}, when a child is carrying a big feeling, a story can sometimes open the door more gently than another lecture or question.",
                    proof_points[0]
                    if proof_points
                    else f"{offer} helps turn one real moment into a personalized story your child can recognize and talk about.",
                    story_prompt_example
                    or "Pick one moment from this week, such as bedtime, friendship, confidence, or school jitters, and Bibblio will help shape it into a story in minutes.",
                ]
        elif campaign_type in {
            "first_story_activation",
            "draft_recovery",
            "download_conversion",
            "credit_purchase_nudge",
            "next_story_idea",
            "referral_invite",
            "winback_parent_moment",
        }:
            body_sections = [
                f"Hi {first_name}, if a real-life moment feels big right now, {offer} can help you turn it into a personalized story your child will actually want to read.",
                proof_points[0]
                if proof_points
                else "It gives you a warm, practical way to support routines, feelings, courage, or friendship without starting from scratch.",
                story_prompt_example
                or (
                    f"For example, you could make a story about bedtime, big feelings, or a new experience and keep it personal to your child."
                ),
            ]
        else:
            body_sections = [
                f"Hi {first_name}, we picked {offer} because it appears to match what matters most for you right now.",
                (
                    proof_points[0]
                    if proof_points
                    else "It is designed to deliver value quickly without adding unnecessary friction."
                ),
                (
                    proof_points[1]
                    if len(proof_points) > 1
                    else str(
                        brief.get("offer_reason")
                        or "This gives you one clear next step instead of a long list of options."
                    )
                ),
            ]
    cta_label = str(
        raw.get("cta_label") or cta_meta.get("label") or "Explore the offer"
    ).strip()
    cta_url_slug = _normalize_slug(
        str(raw.get("cta_url_slug") or cta_meta.get("url_slug") or offer)
    )
    secondary_text = str(
        raw.get("secondary_text")
        or (
            "If you want, just hit reply and tell me a little more about what your child is going through."
            if strategy["campaign_type"] == "reply_followup"
            else brief.get("objection_to_address")
            or "If this is not the right moment, you can still keep it in mind for later."
        )
    ).strip()
    footer_variant = (
        str(raw.get("footer_variant") or "reply").strip() or "reply"
        if campaign_type == "reply_followup"
        else str(raw.get("footer_variant") or "default").strip() or "default"
    )
    signoff = str(raw.get("signoff") or brand.get("signoff_name") or "The Team").strip()
    subject = choose_best_subject(
        subject_candidates, customer=customer, primary_offer=offer
    )
    return {
        "subject_candidates": subject_candidates[:3],
        "subject": subject,
        "selected_subject": subject,
        "preview_text": preview_text[:120],
        "eyebrow": eyebrow[:80],
        "headline": headline[:90],
        "body_sections": body_sections[:3],
        "cta_label": cta_label[:40],
        "cta_url_slug": cta_url_slug,
        "footer_variant": footer_variant,
        "secondary_text": secondary_text[:220],
        "signoff": signoff,
        "body_text": compose_text_body(
            {
                "body_sections": body_sections[:3],
                "cta_label": cta_label[:40],
                "signoff": signoff,
            }
        ),
        "campaign_type": campaign_type,
        "audience_segment": strategy["audience_segment"],
    }


def build_cta_url(
    *,
    base_url: str,
    slug: str,
    campaign_type: str,
    audience_segment: str,
) -> str:
    path = slug.strip().lstrip("/")
    if not path:
        path = "discover"
    params = urlencode(
        {
            "utm_source": "synaptic",
            "utm_medium": "email",
            "utm_campaign": campaign_type,
            "utm_segment": audience_segment,
        }
    )
    return f"{base_url.rstrip('/')}/{path}?{params}"


def build_footer_text(brand: dict[str, Any], variant: str) -> str:
    footer_variants = dict(brand.get("footer_variants", {}))
    return str(
        footer_variants.get(variant)
        or footer_variants.get("default")
        or "You are receiving this because you asked to hear from us."
    )


def build_design_slots(*, plan: dict[str, Any], brand: dict[str, Any]) -> dict[str, Any]:
    draft = plan["draft"]
    base_url = str(brand.get("base_url", "https://example.com"))
    cta_url = build_cta_url(
        base_url=base_url,
        slug=draft["cta_url_slug"],
        campaign_type=plan.get("campaign_type", "product_spotlight"),
        audience_segment=plan.get("audience_segment", "general_audience"),
    )
    unsubscribe_url = (
        f"{base_url.rstrip('/')}/{str(brand.get('unsubscribe_path', 'unsubscribe')).lstrip('/')}"
    )
    preference_center_url = (
        f"{base_url.rstrip('/')}/{str(brand.get('preference_center_path', 'email-preferences')).lstrip('/')}"
    )
    footer_text = build_footer_text(brand, draft.get("footer_variant", "default"))
    return {
        "preheader": draft["preview_text"],
        "eyebrow": draft["eyebrow"],
        "headline": draft["headline"],
        "body_sections": normalize_body_sections(draft.get("body_sections", [])),
        "cta_label": draft["cta_label"],
        "cta_url": cta_url,
        "secondary_text": draft["secondary_text"],
        "footer_text": footer_text,
        "unsubscribe_url": unsubscribe_url,
        "preference_center_url": preference_center_url,
        "signature": draft.get("signoff", brand.get("signoff_name", "The Team")),
    }


def _find_design_template(name: str) -> str | None:
    current = Path(__file__).resolve()
    roots: list[Path] = []
    for env_key in ("MN_WORKDIR", "PWD"):
        env_value = os.environ.get(env_key, "").strip()
        if env_value:
            roots.append(Path(env_value))
    roots.append(Path.cwd())
    for root in roots:
        candidate = root / "input" / "designs" / name
        if candidate.exists():
            return candidate.read_text()
    for parent in [current.parent, *current.parents]:
        candidate = parent / "input" / "designs" / name
        if candidate.exists():
            return candidate.read_text()
    return None


def _render_design_template(source: str, context: dict[str, Any]) -> str:
    def render_body_sections(match: re.Match[str]) -> str:
        block = match.group(1)
        return "".join(
            block.replace("{{body_section}}", html.escape(str(section)))
            for section in normalize_body_sections(context.get("body_sections", []))
        )

    rendered = re.sub(
        r"\{\{#body_sections\}\}(.*?)\{\{/body_sections\}\}",
        render_body_sections,
        source,
        flags=re.DOTALL,
    )

    def render_value(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return html.escape(str(context.get(key, "")))

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", render_value, rendered)


def render_email_html(template: dict[str, Any], slots: dict[str, Any]) -> str:
    template_id = str(template.get("template_id", ""))
    palette = dict(template.get("palette", {}))
    accent = palette.get("accent", "#0f766e")
    accent_soft = palette.get("accent_soft", "#ecfeff")
    text_color = palette.get("text", "#1f2937")
    design_template = str(
        template.get("design_template")
        or ("personal_reply.html" if template_id == "personal_reply" else "card_email.html")
    )
    design_source = _find_design_template(design_template)
    if design_source:
        return _render_design_template(
            design_source,
            {
                **slots,
                "accent": accent,
                "accent_soft": accent_soft,
                "text_color": text_color,
            },
        )
    if template_id == "personal_reply":
        body_sections = "".join(
            f"<p data-slot='body_section' style='margin:0 0 14px;font-size:16px;line-height:1.65;color:{text_color};font-family:Arial,sans-serif;'>{html.escape(section)}</p>"
            for section in normalize_body_sections(slots.get("body_sections", []))
        )
        cta_url = html.escape(str(slots.get("cta_url", "")))
        cta_label = html.escape(str(slots.get("cta_label", "")))
        secondary_text = html.escape(str(slots.get("secondary_text", "")))
        footer_text = html.escape(str(slots.get("footer_text", "")))
        preference_center_url = html.escape(str(slots.get("preference_center_url", "")))
        unsubscribe_url = html.escape(str(slots.get("unsubscribe_url", "")))
        cta_block = (
            f"<p style='margin:16px 0 0;font-size:16px;line-height:1.65;color:{text_color};font-family:Arial,sans-serif;'><a data-slot='cta_button' href='{cta_url}' style='color:{accent};text-decoration:underline;'>{cta_label}</a></p>"
            if cta_url and cta_label
            else ""
        )
        return (
            "<html><body style='margin:0;padding:24px;background-color:#ffffff;'>"
            f"<div style='display:none;max-height:0;overflow:hidden;opacity:0;'>{html.escape(str(slots.get('preheader', '')))}</div>"
            "<div style='max-width:640px;margin:0 auto;'>"
            f"<p data-slot='eyebrow' style='margin:0 0 10px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:{accent};font-family:Arial,sans-serif;'>{html.escape(str(slots.get('eyebrow', '')))}</p>"
            f"<p data-slot='headline' style='margin:0 0 18px;font-size:18px;line-height:1.5;color:{text_color};font-family:Arial,sans-serif;font-weight:600;'>{html.escape(str(slots.get('headline', '')))}</p>"
            f"{body_sections}{cta_block}"
            f"<p data-slot='secondary_text' style='margin:18px 0 0;font-size:15px;line-height:1.6;color:{text_color};font-family:Arial,sans-serif;'>{secondary_text}</p>"
            f"<p style='margin:18px 0 0;font-size:15px;line-height:1.6;color:{text_color};font-family:Arial,sans-serif;'>{html.escape(str(slots.get('signature', '')))}</p>"
            f"<hr style='margin:24px 0;border:none;border-top:1px solid #e5e7eb;' /><p data-slot='footer_text' style='margin:0 0 10px;font-size:12px;line-height:1.6;color:#6b7280;font-family:Arial,sans-serif;'>{footer_text}</p>"
            f"<p style='margin:0;font-size:12px;line-height:1.6;color:#6b7280;font-family:Arial,sans-serif;'><a href='{preference_center_url}' style='color:{accent};'>Manage preferences</a> · <a href='{unsubscribe_url}' style='color:{accent};'>Unsubscribe</a></p>"
            "</div></body></html>"
        )
    body_sections = "".join(
        f"<p data-slot='body_section' style='margin:0 0 16px;font-size:16px;line-height:1.7;color:{text_color};'>{html.escape(section)}</p>"
        for section in normalize_body_sections(slots.get("body_sections", []))
    )
    secondary_text = html.escape(str(slots.get("secondary_text", "")))
    footer_text = html.escape(str(slots.get("footer_text", "")))
    cta_label = html.escape(str(slots.get("cta_label", "")))
    cta_url = html.escape(str(slots.get("cta_url", "")))
    preference_center_url = html.escape(str(slots.get("preference_center_url", "")))
    unsubscribe_url = html.escape(str(slots.get("unsubscribe_url", "")))
    return (
        "<html><body style='margin:0;padding:0;background-color:#f5f1e8;'>"
        f"<div style='display:none;max-height:0;overflow:hidden;opacity:0;'>{html.escape(str(slots.get('preheader', '')))}</div>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background-color:#f5f1e8;padding:24px 0;'>"
        "<tr><td align='center'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='max-width:640px;background:#ffffff;border-radius:18px;overflow:hidden;'>"
        f"<tr><td style='padding:28px 32px 12px;background:{accent_soft};'>"
        f"<div data-slot='eyebrow' style='font-size:12px;letter-spacing:0.12em;text-transform:uppercase;color:{accent};font-weight:700;margin-bottom:12px;'>{html.escape(str(slots.get('eyebrow', '')))}</div>"
        f"<h1 data-slot='headline' style='margin:0;font-size:30px;line-height:1.2;color:{text_color};font-family:Georgia,serif;'>{html.escape(str(slots.get('headline', '')))}</h1>"
        "</td></tr>"
        f"<tr><td style='padding:28px 32px 8px;'>{body_sections}</td></tr>"
        f"<tr><td style='padding:8px 32px 0;'><a data-slot='cta_button' href='{cta_url}' style='display:inline-block;background:{accent};color:#ffffff;text-decoration:none;font-weight:700;padding:14px 22px;border-radius:999px;font-size:15px;'>{cta_label}</a></td></tr>"
        f"<tr><td style='padding:18px 32px 28px;'><p data-slot='secondary_text' style='margin:0;font-size:14px;line-height:1.6;color:#52606d;'>{secondary_text}</p><p style='margin:18px 0 0;font-size:15px;line-height:1.6;color:{text_color};'>{html.escape(str(slots.get('signature', '')))}</p></td></tr>"
        f"<tr><td style='padding:18px 32px 28px;background:#f8fafc;border-top:1px solid #e5e7eb;'><p data-slot='footer_text' style='margin:0 0 12px;font-size:12px;line-height:1.6;color:#52606d;'>{footer_text}</p><p style='margin:0;font-size:12px;line-height:1.6;color:#52606d;'><a href='{preference_center_url}' style='color:{accent};'>Manage preferences</a> · <a href='{unsubscribe_url}' style='color:{accent};'>Unsubscribe</a></p></td></tr>"
        "</table></td></tr></table></body></html>"
    )


def has_placeholder_text(value: str) -> bool:
    lowered = value.lower()
    return any(
        token in lowered
        for token in ["lorem ipsum", "tbd", "placeholder", "[insert", "your company"]
    )


def review_email_quality(
    *,
    plan: dict[str, Any],
    template_library: dict[str, dict[str, Any]],
    latest_source_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    draft = dict(plan.get("draft", {}))
    design = dict(plan.get("design", {}))
    issues: list[str] = []
    score = 100

    for field in ["subject", "preview_text", "headline", "cta_label", "cta_url_slug"]:
        if not draft.get(field):
            issues.append(f"missing_{field}")
            score -= 18

    if not draft.get("body_sections"):
        issues.append("missing_body_sections")
        score -= 20

    template_name = design.get("template")
    if not template_name or template_name not in template_library:
        issues.append("invalid_template")
        score -= 20

    preview_len = len(str(draft.get("preview_text", "")))
    subject_len = len(str(draft.get("subject", "")))
    if plan.get("campaign_type") == "reply_followup":
        subject_out_of_range = subject_len < 6 or subject_len > 120
    else:
        subject_out_of_range = subject_len < 24 or subject_len > 70
    if subject_out_of_range:
        issues.append("subject_length_out_of_range")
        score -= 8
    if preview_len < 30 or preview_len > 120:
        issues.append("preview_length_out_of_range")
        score -= 6

    combined_text = " ".join(
        [
            str(draft.get("subject", "")),
            str(draft.get("preview_text", "")),
            str(draft.get("headline", "")),
            " ".join(str(item) for item in draft.get("body_sections", [])),
        ]
    )
    if has_placeholder_text(combined_text):
        issues.append("placeholder_text_detected")
        score -= 25

    combined_lower = combined_text.lower()
    if any(phrase in combined_lower for phrase in GENERIC_MARKETING_PHRASES):
        issues.append("generic_positioning_language")
        score -= 12
    if plan.get("audience_segment") in {
        "teachers",
        "creators_educators",
        "new_parents",
        "engaged_creators",
        "repeat_story_builders",
        "gift_memory_shoppers",
        "referral_advocates",
    } and not any(
        token in combined_lower
        for token in [
            "story",
            "child",
            "kid",
            "parent",
            "bedtime",
            "friendship",
            "feelings",
            "courage",
            "routine",
        ]
    ):
        issues.append("missing_parent_story_context")
        score -= 10

    if len(draft.get("body_sections", [])) < 2:
        issues.append("insufficient_body_sections")
        score -= 10

    html_body = str(design.get("html_body", ""))
    if "data-slot='cta_button'" not in html_body or "utm_campaign=" not in html_body:
        issues.append("missing_cta_link")
        score -= 18
    if "unsubscribe" not in html_body.lower() or "manage preferences" not in html_body.lower():
        issues.append("missing_footer_compliance")
        score -= 20
    if "data-slot='headline'" not in html_body or "data-slot='body_section'" not in html_body:
        issues.append("missing_core_modules")
        score -= 15

    if latest_source_payload:
        if (
            plan.get("campaign_type") != "reply_followup"
            and latest_source_payload.get("campaign_type") == plan.get("campaign_type")
        ):
            issues.append("repeated_campaign_type")
            score -= 10
        if (
            plan.get("campaign_type") != "reply_followup"
            and latest_source_payload.get("primary_offer") == plan.get("primary_offer")
        ):
            issues.append("repeated_primary_offer")
            score -= 10
        latest_template = latest_source_payload.get("design", {}).get("template")
        if (
            plan.get("campaign_type") != "reply_followup"
            and latest_template
            and latest_template == template_name
        ):
            issues.append("repeated_template")
            score -= 8

    return {"score": max(score, 0), "issues": issues, "passed": max(score, 0) >= 70}


def parse_source_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def has_thread_reply_context(plan: dict[str, Any]) -> bool:
    reply_context = plan.get("reply_context") or {}
    if not isinstance(reply_context, dict):
        return False
    for key in ("thread_message_id", "in_reply_to_message_id", "message_id"):
        if str(reply_context.get(key) or "").strip():
            return True
    references = reply_context.get("references_message_ids")
    return isinstance(references, list) and any(str(ref or "").strip() for ref in references)


def allows_personal_reply_template(plan: dict[str, Any]) -> bool:
    return plan.get("campaign_type") == "reply_followup" and has_thread_reply_context(plan)


def select_template_name(
    *,
    plan: dict[str, Any],
    template_library: dict[str, dict[str, Any]],
) -> str:
    recommended = plan.get("customer_brief", {}).get("recommended_template")
    if recommended == "personal_reply" and not allows_personal_reply_template(plan):
        recommended = None
    if recommended in template_library:
        return str(recommended)

    mapping = {
        "product_spotlight": "product_spotlight",
        "program_reminder": "program_reminder",
        "interest_followup": "interest_followup",
        "reply_followup": (
            "personal_reply" if allows_personal_reply_template(plan) else "product_spotlight"
        ),
        "parent_awareness": "moment_to_story",
        "parent_education": "finish_your_book",
        "parent_activation": "moment_to_story",
        "parent_social_proof": "story_reveal",
        "parent_use_case": "moment_to_story",
        "parent_reminder": "finish_your_book",
        "parent_expansion": "share_the_magic",
        "teacher_awareness": "program_reminder",
        "teacher_education": "interest_followup",
        "teacher_activation": "moment_to_story",
        "teacher_social_proof": "story_reveal",
        "teacher_use_case": "product_spotlight",
        "teacher_reminder": "interest_followup",
        "teacher_expansion": "share_the_magic",
        "creator_awareness": "program_reminder",
        "creator_education": "product_spotlight",
        "creator_activation": "moment_to_story",
        "creator_social_proof": "story_reveal",
        "creator_use_case": "product_spotlight",
        "creator_reminder": "finish_your_book",
        "creator_expansion": "share_the_magic",
        "first_story_activation": "moment_to_story",
        "draft_recovery": "finish_your_book",
        "download_conversion": "story_reveal",
        "credit_purchase_nudge": "more_credits_more_stories",
        "next_story_idea": "moment_to_story",
        "referral_invite": "share_the_magic",
        "winback_parent_moment": "moment_to_story",
    }
    mapped = mapping.get(plan.get("campaign_type", "product_spotlight"))
    if mapped in template_library:
        return str(mapped)
    return next(iter(template_library.keys()), "product_spotlight")
