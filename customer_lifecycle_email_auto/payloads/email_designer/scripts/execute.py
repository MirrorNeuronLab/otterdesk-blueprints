#!/usr/bin/env python3
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _synaptic_runtime.core import (
    load_input_plan,
    load_knowledge_section,
    load_template_library,
    log_agent,
)
from _synaptic_skills.marketing_email import (
    build_design_slots,
    render_email_html,
    select_template_name,
)


AGENT_ID = "email_designer_agent"

def main() -> None:
    plan = load_input_plan()
    runtime_job_id = plan.get("runtime_job_id")

    if plan.get("existing_draft"):
        log_agent(runtime_job_id, AGENT_ID, "Skipped email design because a ready draft already exists.")
        print(json.dumps(plan))
        return

    template_library = load_template_library()
    brand = load_knowledge_section("brand")
    template_name = select_template_name(plan=plan, template_library=template_library)
    template = template_library.get(template_name, {})
    slots = build_design_slots(plan=plan, brand=brand)
    html_body = render_email_html(template, slots)
    plan["design"] = {
        "template": template_name,
        "slots": slots,
        "html_body": html_body,
    }
    plan["draft"]["body_text"] = plan["draft"].get("body_text") or ""
    log_agent(
        runtime_job_id,
        AGENT_ID,
        "Prepared deterministic email design from template.",
        details={"template": template_name},
    )
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
