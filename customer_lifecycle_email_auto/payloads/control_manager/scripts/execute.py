#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _synaptic_runtime.core import (
    latest_sent_draft,
    load_input_plan,
    load_knowledge_section,
    load_template_library,
    log_agent,
    pending_ready_draft,
    read_email_rules,
    save_ready_draft,
    utc_now,
)
from _synaptic_skills.marketing_email import (
    build_design_slots,
    normalize_structured_draft,
    parse_source_payload,
    render_email_html,
    review_email_quality,
    select_template_name,
)


AGENT_ID = "control_manager_agent"


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def repair_low_quality_email(plan: dict) -> dict:
    brand = load_knowledge_section("brand")
    template_library = load_template_library()
    repaired_draft = normalize_structured_draft({}, plan=plan, brand=brand)
    plan["draft"] = repaired_draft
    template_name = select_template_name(plan=plan, template_library=template_library)
    slots = build_design_slots(plan=plan, brand=brand)
    plan["design"] = {
        "template": template_name,
        "slots": slots,
        "html_body": render_email_html(template_library.get(template_name, {}), slots),
    }
    return plan


def minimum_gap_minutes(rules: dict) -> int:
    try:
        return max(0, int(rules.get("minimum_minutes_between_emails", 5)))
    except (TypeError, ValueError):
        return 5


def test_recipient_mode() -> bool:
    return bool(os.environ.get("SYNAPTIC_TEST_EMAIL_TO", "").strip())


def print_plan_with_delivery_emit(plan: dict) -> None:
    body = dict(plan)
    body.pop("emit_messages", None)
    result = dict(plan)
    result["emit_messages"] = [
        {
            "to": "marketing_automation_agent",
            "type": "control_manager_result",
            "body": body,
            "class": "event",
            "headers": {
                "schema_ref": "com.synaptic.control_manager.result",
                "schema_version": "1.0.0",
            },
        }
    ]
    print(json.dumps(result))


def main() -> None:
    plan = load_input_plan()
    customer = plan["customer"]
    runtime_job_id = plan.get("runtime_job_id")
    rules = read_email_rules()
    minimum_gap = minimum_gap_minutes(rules)
    is_test_mode = test_recipient_mode()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    existing_draft = plan.get("existing_draft") or pending_ready_draft(customer["customer_id"])
    if existing_draft is not None:
        scheduled_send_at = parse_time(existing_draft["scheduled_send_at"]) or now
        decision = "send_now" if is_test_mode or scheduled_send_at <= now else "wait"
        plan["saved_draft"] = existing_draft
        plan["control_decision"] = {
            "decision": decision,
            "scheduled_send_at": existing_draft["scheduled_send_at"],
            "rule_name": "minimum_minutes_between_emails",
            "test_recipient_mode": is_test_mode,
        }
        log_agent(
            runtime_job_id,
            AGENT_ID,
            "Evaluated existing ready draft.",
            details={"decision": decision, "scheduled_send_at": existing_draft["scheduled_send_at"]},
        )
        print_plan_with_delivery_emit(plan)
        return

    draft = plan.get("draft", {})
    design = plan.get("design", {})
    template_library = load_template_library()
    latest_sent = latest_sent_draft(customer["customer_id"])
    latest_source_payload = parse_source_payload(
        (latest_sent or {}).get("source_payload_json") if latest_sent else None
    )
    review = review_email_quality(
        plan=plan,
        template_library=template_library,
        latest_source_payload=latest_source_payload,
    )
    if not review["passed"]:
        plan = repair_low_quality_email(plan)
        draft = plan.get("draft", {})
        design = plan.get("design", {})
        review = review_email_quality(
            plan=plan,
            template_library=template_library,
            latest_source_payload=latest_source_payload,
        )
        log_agent(
            runtime_job_id,
            AGENT_ID,
            "Repaired low-quality email before saving draft.",
            details={"quality_score": review["score"], "issues": review["issues"]},
        )
    if is_test_mode or plan.get("campaign_type") == "reply_followup":
        earliest_send_at = now
    else:
        last_sent_at = parse_time(latest_sent["sent_at"]) if latest_sent else None
        earliest_send_at = (
            now if last_sent_at is None else max(now, last_sent_at + timedelta(minutes=minimum_gap))
        )

    saved_draft = save_ready_draft(
        draft_id=f"draft_{uuid.uuid4().hex[:12]}",
        customer_id=customer["customer_id"],
        runtime_job_id=runtime_job_id,
        subject=draft["subject"],
        preview_text=draft["preview_text"],
        body_text=draft["body_text"],
        html_body=design.get("html_body", ""),
        scheduled_send_at=iso(earliest_send_at),
        source_payload=plan,
    )

    plan["saved_draft"] = saved_draft
    plan["control_decision"] = {
        "decision": "send_now" if earliest_send_at <= now else "wait",
        "scheduled_send_at": saved_draft["scheduled_send_at"],
        "rule_name": "minimum_minutes_between_emails",
        "quality_score": review["score"],
        "quality_issues": review["issues"],
        "test_recipient_mode": is_test_mode,
    }
    plan["prepared_at"] = utc_now()
    log_agent(
        runtime_job_id,
        AGENT_ID,
        "Saved draft and applied send interval rule.",
        details={
            "scheduled_send_at": saved_draft["scheduled_send_at"],
            "rule_name": "minimum_minutes_between_emails",
            "quality_score": review["score"],
        },
    )
    print_plan_with_delivery_emit(plan)


if __name__ == "__main__":
    main()
