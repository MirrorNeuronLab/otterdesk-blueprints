#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


BLUEPRINT_DIR = Path(__file__).resolve().parent
EMAIL_DESIGNER_PAYLOAD = BLUEPRINT_DIR / "payloads" / "email_designer"
sys.path.insert(0, str(EMAIL_DESIGNER_PAYLOAD))

from _synaptic_runtime.core import load_knowledge_section, load_template_library  # noqa: E402
from _synaptic_skills.marketing_email import build_design_slots, render_email_html  # noqa: E402


SAMPLE_BY_AUDIENCE = {
    "parents": {
        "customer": {
            "customer_id": "preview_parent",
            "name": "Maya Thompson",
            "email": "maya@example.com",
            "job_title": "Parent",
        },
        "headline": "What your child does not say out loud",
        "body_sections": [
            "Hi Maya, when a child has a hard day, the clearest signal is not always a sentence. Sometimes it shows up as bedtime resistance, worry, silence, or a sudden big feeling.",
            "Bibblio helps turn that real moment into a personalized emotional learning story, so your child can see the feeling from a safer distance and find words for it.",
            "Choose one moment from this week and start with a five-minute story prompt.",
        ],
        "cta_label": "Create a story for tonight",
    },
    "teachers": {
        "customer": {
            "customer_id": "preview_teacher",
            "name": "Mr. Davis",
            "email": "teacher@example.com",
            "job_title": "Teacher",
        },
        "headline": "Why students remember stories but forget lessons",
        "body_sections": [
            "Hi Mr. Davis, students often remember a story long after a lesson fades. That is why Bibblio is built around classroom moments, not generic content.",
            "Use story-based prompts for friendship, anxiety, bullying, confidence, or belonging without adding a heavy new curriculum.",
            "Start with one five-minute emotional check-in and let students discuss the choice the character makes next.",
        ],
        "cta_label": "See classroom story ideas",
    },
    "creators_educators": {
        "customer": {
            "customer_id": "preview_creator",
            "name": "Alex Rivera",
            "email": "creator@example.com",
            "job_title": "Creator",
        },
        "headline": "Turn real childhood struggles into meaningful stories",
        "body_sections": [
            "Hi Alex, emotional learning content is becoming its own category: stories that help children understand real struggles through narrative.",
            "Bibblio gives creators a practical way to build around themes parents and teachers already need, from anxiety and friendship to courage and transitions.",
            "Choose one emotional theme and publish a story that gives children language for the moment.",
        ],
        "cta_label": "Choose a story theme",
    },
}


def choose_sample(template: dict[str, Any]) -> dict[str, Any]:
    audiences = template.get("recommended_audiences") or []
    for audience in audiences:
        if audience in SAMPLE_BY_AUDIENCE:
            return SAMPLE_BY_AUDIENCE[audience]
    return SAMPLE_BY_AUDIENCE["parents"]


def build_preview_plan(template_id: str, template: dict[str, Any]) -> dict[str, Any]:
    sample = choose_sample(template)
    campaign_type = (template.get("recommended_campaigns") or [template_id])[0]
    audience_segment = (template.get("recommended_audiences") or ["parents"])[0]
    phase = (template.get("recommended_phases") or ["preview"])[0]
    name = template.get("name") or template_id.replace("_", " ").title()

    return {
        "runtime_job_id": "preview",
        "campaign_type": campaign_type,
        "audience_segment": audience_segment,
        "goal": template.get("purpose", "Preview this email design."),
        "customer": sample["customer"],
        "draft": {
            "subject": f"Preview: {name}",
            "preview_text": f"Previewing the {name} email layout.",
            "eyebrow": str(phase).replace("_", " ").title(),
            "headline": sample["headline"],
            "body_sections": sample["body_sections"],
            "cta_label": sample["cta_label"],
            "cta_url_slug": "preview",
            "secondary_text": template.get("purpose", "Review spacing, typography, and CTA treatment."),
            "footer_variant": "default",
            "signoff": "Maya",
        },
    }


def write_index(output_dir: Path, rendered: list[dict[str, str]]) -> None:
    rows = []
    for item in rendered:
        rows.append(
            "<tr>"
            f"<td><a href=\"{html.escape(item['file'])}\">{html.escape(item['template_id'])}</a></td>"
            f"<td>{html.escape(item['name'])}</td>"
            f"<td>{html.escape(item['design_template'])}</td>"
            f"<td>{html.escape(item['audience'])}</td>"
            "</tr>"
        )
    index = (
        "<html><head><title>Bibblio Email Previews</title>"
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2937}"
        "table{border-collapse:collapse;width:100%;max-width:960px}"
        "th,td{border-bottom:1px solid #e5e7eb;text-align:left;padding:10px 12px}"
        "th{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#6b7280}"
        "a{color:#2563eb}</style></head><body>"
        "<h1>Bibblio Email Previews</h1>"
        "<p>Generated from input/templates and input/designs.</p>"
        "<table><thead><tr><th>Template</th><th>Name</th><th>Design</th><th>Audience</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</body></html>"
    )
    (output_dir / "index.html").write_text(index)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render all business email templates into local HTML previews."
    )
    parser.add_argument(
        "--output-dir",
        default=str(BLUEPRINT_DIR / "previews"),
        help="Directory to write preview HTML files. Defaults to ./previews.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    template_library = load_template_library()
    brand = load_knowledge_section("brand")
    rendered: list[dict[str, str]] = []

    for template_id in sorted(template_library):
        template = template_library[template_id]
        plan = build_preview_plan(template_id, template)
        slots = build_design_slots(plan=plan, brand=brand)
        html_body = render_email_html(template, slots)
        filename = f"{template_id}.html"
        (output_dir / filename).write_text(html_body)
        rendered.append(
            {
                "template_id": template_id,
                "name": str(template.get("name") or template_id),
                "design_template": str(template.get("design_template") or "card_email.html"),
                "audience": str(plan.get("audience_segment") or ""),
                "file": filename,
            }
        )

    write_index(output_dir, rendered)
    print(f"Rendered {len(rendered)} email previews to {output_dir}")
    print(f"Open {output_dir / 'index.html'}")


if __name__ == "__main__":
    main()
