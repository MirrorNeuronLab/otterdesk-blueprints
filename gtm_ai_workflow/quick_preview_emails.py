#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import Any


BLUEPRINT_DIR = Path(__file__).resolve().parent
EMAIL_DESIGNER_PAYLOAD = BLUEPRINT_DIR / "payloads" / "email_designer"
sys.path.insert(0, str(EMAIL_DESIGNER_PAYLOAD))

from _synaptic_runtime.core import load_knowledge_section, load_template_library  # noqa: E402
from _synaptic_skills.marketing_email import build_design_slots, render_email_html  # noqa: E402


SAMPLE_BY_AUDIENCE = {
    "sales_ops": {
        "customer": {
            "customer_id": "preview_sales_ops",
            "name": "Riley Chen",
            "email": "riley@example.com",
            "company": "Luma Systems",
            "job_title": "VP Revenue Operations",
        },
        "headline": "Keep AI outbound tied to CRM truth",
        "body_sections": [
            "Hi Riley, when reps test AI outbound faster than CRM state gets updated, account context starts to drift.",
            "GTM AI Workflow keeps the loop together: account signal, outreach, reply summary, next action, and local CRM CSV update.",
            "A small pilot can start with a handful of target accounts before anything touches production systems.",
        ],
        "cta_label": "Review the CRM loop",
    },
    "product_marketing": {
        "customer": {
            "customer_id": "preview_pmm",
            "name": "Mina Patel",
            "email": "mina@example.com",
            "company": "Northstar Analytics",
            "job_title": "Head of Product Marketing",
        },
        "headline": "Turn sales replies into positioning signal",
        "body_sections": [
            "Hi Mina, the strongest product-marketing language often appears inside sales replies and call notes.",
            "This workflow summarizes replies and writes structured insight rows so product and marketing can review repeated pains, objections, and phrasing.",
            "The result is better outreach and a sharper positioning loop.",
        ],
        "cta_label": "Review the signal loop",
    },
    "founders": {
        "customer": {
            "customer_id": "preview_founder",
            "name": "Alex Morgan",
            "email": "alex@example.com",
            "company": "Cascade Robotics",
            "job_title": "Co-founder and CEO",
        },
        "headline": "Learn from every founder-led sales cycle",
        "body_sections": [
            "Hi Alex, early GTM motions need learning velocity as much as they need more outbound.",
            "GTM AI Workflow connects target-account research, sales email drafts, replies, CRM state, and product insight in one local loop.",
            "Start with a small target list and inspect what the market is actually telling you.",
        ],
        "cta_label": "Start with a target list",
    },
}


def choose_sample(template: dict[str, Any]) -> dict[str, Any]:
    audiences = template.get("recommended_audiences") or []
    for audience in audiences:
        if audience in SAMPLE_BY_AUDIENCE:
            return SAMPLE_BY_AUDIENCE[audience]
    return SAMPLE_BY_AUDIENCE["sales_ops"]


def build_preview_plan(template_id: str, template: dict[str, Any]) -> dict[str, Any]:
    sample = choose_sample(template)
    campaign_type = (template.get("recommended_campaigns") or [template_id])[0]
    audience_segment = (template.get("recommended_audiences") or ["sales_ops"])[0]
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
            "preview_text": f"Previewing the {name} GTM email layout.",
            "eyebrow": str(phase).replace("_", " ").title(),
            "headline": sample["headline"],
            "body_sections": sample["body_sections"],
            "cta_label": sample["cta_label"],
            "cta_url_slug": "preview",
            "secondary_text": template.get("purpose", "Review spacing, typography, and CTA treatment."),
            "footer_variant": "default",
            "signoff": "The GTM AI team",
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
        "<html><head><title>GTM AI Email Previews</title>"
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2937}"
        "table{border-collapse:collapse;width:100%;max-width:960px}"
        "th,td{border-bottom:1px solid #e5e7eb;text-align:left;padding:10px 12px}"
        "th{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#6b7280}"
        "a{color:#2563eb}</style></head><body>"
        "<h1>GTM AI Email Previews</h1>"
        "<p>Generated from input/templates and input/designs.</p>"
        "<table><thead><tr><th>Template</th><th>Name</th><th>Design</th><th>Audience</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</body></html>"
    )
    (output_dir / "index.html").write_text(index)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render GTM outreach templates into local HTML previews.")
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
