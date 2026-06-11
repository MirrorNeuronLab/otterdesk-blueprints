#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _synaptic_runtime.core import (
    add_marketing_activity,
    db_connect,
    load_input_plan,
    load_knowledge_section,
    log_agent,
    mark_draft_sent,
    pending_ready_draft,
    read_delivery_settings,
    utc_now,
)
from _synaptic_skills.email_delivery import dry_run_email, post_email, post_slack_message
from _synaptic_skills.marketing_email import (
    build_design_slots,
    render_email_html,
    select_template_name,
)


AGENT_ID = "marketing_automation_agent"


def safe_artifact_slug(value: object, fallback: str = "email") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-")
    return slug[:80] or fallback


def sent_email_copy_root(runtime_job_id: str | None) -> Path:
    override = os.environ.get("SYNAPTIC_SENT_EMAIL_COPY_DIR", "").strip()
    if override:
        return Path(override)
    job_id = safe_artifact_slug(
        runtime_job_id
        or os.environ.get("MN_JOB_ID")
        or os.environ.get("SYNAPTIC_JOB_ID"),
        "mn-business-email-local",
    )
    job_folder = job_id if job_id.startswith("mn_") else f"mn_{job_id}"
    return Path("/tmp") / job_folder


def save_sent_email_copy(
    *,
    runtime_job_id: str | None,
    cycle: int,
    customer: dict,
    saved_draft: dict,
    actual_recipient: str,
    execution_request: dict,
    delivery: dict,
    plan: dict,
) -> dict:
    root = sent_email_copy_root(runtime_job_id)
    email_dir = root / "sent_emails"
    email_dir.mkdir(parents=True, exist_ok=True)

    timestamp = utc_now()
    prefix = "-".join(
        [
            timestamp.replace("-", "").replace(":", "").replace("+00:00", "Z"),
            f"cycle-{cycle}",
            safe_artifact_slug(customer.get("customer_id"), "customer"),
            safe_artifact_slug(saved_draft.get("draft_id"), "draft"),
            str(time.time_ns()),
        ]
    )
    html_path = email_dir / f"{prefix}.html"
    text_path = email_dir / f"{prefix}.txt"
    metadata_path = email_dir / f"{prefix}.json"

    html_body = str(execution_request.get("html") or "")
    text_body = str(execution_request.get("text") or "")
    html_path.write_text(html_body, encoding="utf-8")
    text_path.write_text(text_body, encoding="utf-8")
    metadata = {
        "timestamp": timestamp,
        "runtime_job_id": runtime_job_id,
        "cycle": cycle,
        "agent_id": AGENT_ID,
        "customer_id": customer.get("customer_id"),
        "customer_email": customer.get("email"),
        "recipient": actual_recipient,
        "subject": saved_draft.get("subject"),
        "draft_id": saved_draft.get("draft_id"),
        "campaign_type": plan.get("campaign_type"),
        "template": (plan.get("design") or {}).get("template")
        if isinstance(plan.get("design"), dict)
        else None,
        "provider_id": delivery.get("provider_id"),
        "delivery_status": delivery.get("status"),
        "headers": execution_request.get("headers", {}),
        "html_path": str(html_path),
        "text_path": str(text_path),
        "has_card_email_marker": "Story moments to explore" in html_body,
        "has_card_gradient": "background-image:linear-gradient(135deg,#dff5fb" in html_body,
        "has_personal_reply_marker": (
            "data-slot=\"body_section\"" in html_body
            and "Story moments to explore" not in html_body
        ),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "saved",
        "root": str(root),
        "html_path": str(html_path),
        "text_path": str(text_path),
        "metadata_path": str(metadata_path),
        "html_content": html_body,
        "text_content": text_body,
        "metadata": metadata,
    }


def safe_save_sent_email_copy(**kwargs) -> dict:
    try:
        return save_sent_email_copy(**kwargs)
    except Exception as exc:
        return {"status": "failed", "reason": "sent_email_copy_error", "error": str(exc)}


def quick_testing_enabled(delivery_settings: dict) -> bool:
    values = [
        os.environ.get("SYNAPTIC_QUICK_TEST_MODE", ""),
        os.environ.get("SYNAPTIC_EMAIL_DRY_RUN", ""),
        str(delivery_settings.get("quick_testing", "")),
        str(delivery_settings.get("dry_run", "")),
    ]
    mode = (
        os.environ.get("SYNAPTIC_EMAIL_DELIVERY_MODE", "")
        or str(delivery_settings.get("mode", ""))
    ).strip().lower()
    if mode in {"agentmail", "live"}:
        return False
    return mode in {"dry_run", "dry-run", "test", "quick_test"} or any(
        value.strip().lower() in {"1", "true", "yes", "on"} for value in values
    )


def log_email_sent_event(runtime_job_id: str | None, to_email: str, subject: str) -> None:
    log_agent(
        runtime_job_id,
        AGENT_ID,
        "Email sent event.",
        details={"to": to_email, "subject": subject},
    )


def is_last_campaign_step(campaign_type: str | None) -> bool:
    return campaign_type in {
        "parent_expansion",
        "teacher_expansion",
        "creator_expansion",
    }


def parse_positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def max_test_cycles() -> int:
    return parse_positive_int(os.environ.get("SYNAPTIC_MAX_TEST_CYCLES")) or 3


def should_emit_cycle_trigger(
    *,
    delivery_status: str | None,
    cycle: int,
    fast_test_sequence: bool,
    campaign_type: str | None,
) -> bool:
    if os.environ.get("SYNAPTIC_EMIT_CYCLE_TRIGGER", "true").lower() == "false":
        return False
    if delivery_status != "sent":
        return False
    if fast_test_sequence and cycle >= max_test_cycles():
        return False
    return not (
        fast_test_sequence
        and is_last_campaign_step(campaign_type)
    )


def resolve_delivery_plan(payload: dict) -> dict:
    """Unwrap MirrorNeuron executor envelopes until a sendable plan is found."""

    candidates = [payload]
    seen_ids: set[int] = set()
    fallback_customer_plan: dict | None = None
    while candidates:
        candidate = candidates.pop(0)
        if not isinstance(candidate, dict):
            continue
        marker = id(candidate)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)

        if isinstance(candidate.get("customer"), dict) and isinstance(
            candidate.get("saved_draft"), dict
        ):
            return candidate
        if isinstance(candidate.get("customer"), dict) and fallback_customer_plan is None:
            fallback_customer_plan = candidate

        sandbox_stdout = str(candidate.get("sandbox", {}).get("stdout") or "").strip()
        if sandbox_stdout:
            try:
                decoded = json.loads(sandbox_stdout)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                candidates.append(decoded)

        for key in ("original_plan", "input", "body", "payload", "plan"):
            nested = candidate.get(key)
            if isinstance(nested, dict):
                if key == "original_plan" and candidate.get("cycle") is not None:
                    nested = dict(nested)
                    nested["cycle"] = candidate["cycle"]
                candidates.append(nested)

    return fallback_customer_plan or payload


def missing_plan_result(plan: dict, reason: str) -> dict:
    cycle = cycle_number(plan)
    return {
        "events": [
            {
                "type": "email_delivery_skipped",
                "payload": {
                    "status": "skipped",
                    "reason": reason,
                    "cycle": cycle,
                },
            }
        ],
        "emit_messages": [],
        "next_state": {
            "last_cycle": cycle,
            "last_status": "skipped",
            "reason": reason,
        },
    }


def cycle_number(plan: dict) -> int:
    cycle = plan.get("cycle", 1)
    try:
        return int(cycle)
    except (TypeError, ValueError):
        return 1


def delivery_count_bucket(status: str | None) -> str:
    return "success" if status == "sent" else "failed"


def record_round_delivery_attempt(
    *,
    runtime_job_id: str | None,
    cycle: int,
    customer_id: str,
    draft_id: str,
    status: str | None,
) -> dict:
    job_key = str(runtime_job_id or "local")
    bucket = delivery_count_bucket(status)
    timestamp = utc_now()
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_round_delivery_attempts (
                runtime_job_id TEXT NOT NULL,
                cycle INTEGER NOT NULL,
                customer_id TEXT NOT NULL,
                draft_id TEXT NOT NULL,
                status TEXT NOT NULL,
                count_bucket TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (runtime_job_id, cycle, customer_id, draft_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO email_round_delivery_attempts (
                runtime_job_id,
                cycle,
                customer_id,
                draft_id,
                status,
                count_bucket,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(runtime_job_id, cycle, customer_id, draft_id) DO UPDATE SET
                status = excluded.status,
                count_bucket = excluded.count_bucket,
                updated_at = excluded.updated_at
            """,
            (
                job_key,
                cycle,
                customer_id,
                draft_id,
                str(status or "unknown"),
                bucket,
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN count_bucket = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN count_bucket = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                COUNT(*) AS attempted_count
            FROM email_round_delivery_attempts
            WHERE runtime_job_id = ?
              AND cycle = ?
            """,
            (job_key, cycle),
        ).fetchone()
        conn.commit()

    return {
        "runtime_job_id": job_key,
        "cycle": cycle,
        "success_count": int(row["success_count"] or 0),
        "failed_count": int(row["failed_count"] or 0),
        "attempted_count": int(row["attempted_count"] or 0),
    }


def format_round_slack_report(
    *, round_stats: dict, customer: dict, actual_recipient: str, status: str
) -> str:
    readable_status = {
        "sent": "sent",
        "failed": "failed",
        "blocked": "blocked",
        "waiting": "waiting",
        "skipped": "skipped",
    }.get(status, status or "unknown")
    return (
        f"Business email campaign round {round_stats['cycle']} report: "
        f"{round_stats['success_count']} succeeded, "
        f"{round_stats['failed_count']} failed "
        f"({round_stats['attempted_count']} attempted). "
        f"Latest: {customer.get('name', 'Unknown customer')} <{actual_recipient}> "
        f"was {readable_status}."
    )


def safe_send_slack_round_report(send_slack, message: str) -> dict:
    try:
        return send_slack(message) or {}
    except Exception as exc:
        return {
            "status": "failed",
            "reason": "slack_report_error",
            "error": str(exc),
        }


def parse_json_object(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def html_matches_design_template(html_body: str, design_template: str) -> bool:
    if not html_body:
        return False
    if design_template == "card_email.html":
        return (
            "Story moments to explore" in html_body
            and "background-image:linear-gradient(135deg,#dff5fb" in html_body
        )
    if design_template == "personal_reply.html":
        return (
            "data-slot=\"body_section\"" in html_body
            and "Story moments to explore" not in html_body
            and "Manage preferences" not in html_body
            and "Unsubscribe" not in html_body
        )
    return "data-slot=" in html_body or "data-slot='" in html_body


def has_thread_reply_context(plan: dict) -> bool:
    reply_context = plan.get("reply_context") or {}
    if not isinstance(reply_context, dict):
        return False
    for key in ("thread_message_id", "in_reply_to_message_id", "message_id"):
        if str(reply_context.get(key) or "").strip():
            return True
    references = reply_context.get("references_message_ids")
    return isinstance(references, list) and any(str(ref or "").strip() for ref in references)


def normalize_delivery_render_plan(render_plan: dict) -> dict:
    if render_plan.get("campaign_type") != "reply_followup" or has_thread_reply_context(render_plan):
        return render_plan

    normalized = dict(render_plan)
    normalized["campaign_type"] = "product_spotlight"

    customer_brief = dict(normalized.get("customer_brief") or {})
    if customer_brief.get("recommended_template") == "personal_reply":
        customer_brief.pop("recommended_template", None)
    normalized["customer_brief"] = customer_brief

    design = dict(normalized.get("design") or {})
    if design.get("template") == "personal_reply":
        design.pop("template", None)
    normalized["design"] = design
    return normalized


def plan_with_source_payload(plan: dict, saved_draft: dict) -> dict:
    source_payload = parse_json_object(saved_draft.get("source_payload_json"))
    if not source_payload:
        return plan
    merged = dict(source_payload)
    merged.update({key: value for key, value in plan.items() if value not in (None, "", {})})
    return merged


def render_delivery_html(plan: dict, saved_draft: dict, brand: dict) -> str:
    """Return template-rendered HTML for delivery when enough draft context exists."""

    saved_html = str(saved_draft.get("html_body") or "")
    initial_design = plan.get("design") if isinstance(plan.get("design"), dict) else {}
    design_html = str(initial_design.get("html_body") or "")
    render_plan = plan_with_source_payload(plan, saved_draft)
    render_plan = normalize_delivery_render_plan(render_plan)
    design = render_plan.get("design") if isinstance(render_plan.get("design"), dict) else {}
    design_html = str(design.get("html_body") or design_html)

    draft = render_plan.get("draft") if isinstance(render_plan.get("draft"), dict) else {}
    draft = {
        "subject": saved_draft.get("subject", ""),
        "preview_text": saved_draft.get("preview_text", ""),
        "eyebrow": render_plan.get("campaign_type", "A useful next step"),
        "headline": saved_draft.get("subject", ""),
        "body_sections": [saved_draft.get("body_text", "")],
        "cta_label": "Open Bibblio",
        "cta_url_slug": "discover",
        "secondary_text": "",
        "footer_variant": "default",
        "signoff": brand.get("signoff_name", "The Team"),
        **draft,
    }
    render_plan["draft"] = draft

    try:
        from _synaptic_runtime.core import load_template_library

        template_library = load_template_library()
        template_name = str(design.get("template") or "")
        if template_name not in template_library:
            template_name = select_template_name(
                plan=render_plan,
                template_library=template_library,
            )
        if template_name not in template_library:
            return design_html or saved_html
        design_template = str(
            template_library[template_name].get("design_template") or "card_email.html"
        )
        if html_matches_design_template(design_html, design_template):
            return design_html
        if html_matches_design_template(saved_html, design_template):
            return saved_html
        slots = build_design_slots(plan=render_plan, brand=brand)
        return render_email_html(template_library[template_name], slots)
    except Exception:
        return design_html or saved_html


def delivery_draft(plan: dict, saved_draft: dict, brand: dict) -> dict:
    hydrated = dict(saved_draft)
    hydrated["html_body"] = render_delivery_html(plan, saved_draft, brand)
    return hydrated


def test_action_key(plan: dict) -> str:
    runtime_job_id = str(plan.get("runtime_job_id") or "local").strip() or "local"
    customer = plan.get("customer") if isinstance(plan.get("customer"), dict) else {}
    customer_id = str(customer.get("customer_id") or "unknown").strip() or "unknown"
    cycle = cycle_number(plan)
    for key in ("campaign_type", "action_type", "plan_id"):
        value = str(plan.get(key) or "").strip()
        if value:
            return f"{runtime_job_id}:cycle:{cycle}:customer:{customer_id}:action:{value}"
    return f"{runtime_job_id}:cycle:{cycle}:customer:{customer_id}"


def reserve_test_delivery_action(
    *, test_recipient: str, plan: dict, saved_draft: dict
) -> tuple[bool, str]:
    action_key = test_action_key(plan)
    timestamp = utc_now()
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_delivery_actions (
                test_recipient TEXT NOT NULL,
                action_key TEXT NOT NULL,
                customer_id TEXT,
                draft_id TEXT,
                subject TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (test_recipient, action_key)
            )
            """
        )
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO test_delivery_actions (
                test_recipient,
                action_key,
                customer_id,
                draft_id,
                subject,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?)
            """,
            (
                test_recipient,
                action_key,
                str(plan.get("customer", {}).get("customer_id") or ""),
                str(saved_draft.get("draft_id") or ""),
                str(saved_draft.get("subject") or ""),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
    return cursor.rowcount == 1, action_key


def complete_test_delivery_action(
    *, test_recipient: str, action_key: str, status: str
) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE test_delivery_actions
            SET status = ?,
                updated_at = ?
            WHERE test_recipient = ?
              AND action_key = ?
            """,
            (status, utc_now(), test_recipient, action_key),
        )
        conn.commit()


def duplicate_test_action_result(
    *, plan: dict, saved_draft: dict, test_recipient: str, action_key: str
) -> dict:
    cycle = cycle_number(plan)
    return {
        "events": [
            {
                "type": "email_delivery_skipped",
                "payload": {
                    "status": "skipped",
                    "reason": "duplicate_test_action",
                    "action_key": action_key,
                    "cycle": cycle,
                    "email": test_recipient,
                    "customer_id": plan.get("customer", {}).get("customer_id"),
                    "subject": saved_draft.get("subject"),
                    "test_recipient_override": True,
                },
            }
        ],
        "emit_messages": [],
        "next_state": {
            "last_cycle": cycle,
            "last_status": "skipped",
            "reason": "duplicate_test_action",
            "action_key": action_key,
        },
    }


def hydrate_saved_draft_from_db(plan: dict) -> dict:
    if isinstance(plan.get("saved_draft"), dict):
        return plan
    customer = plan.get("customer")
    if not isinstance(customer, dict):
        return plan
    customer_id = str(customer.get("customer_id") or "").strip()
    if not customer_id:
        return plan
    ready_draft = pending_ready_draft(customer_id)
    if ready_draft is None:
        return plan
    hydrated = dict(plan)
    hydrated["saved_draft"] = ready_draft
    hydrated.setdefault(
        "control_decision",
        {
            "decision": "send_now",
            "scheduled_send_at": ready_draft.get("scheduled_send_at"),
            "rule_name": "pending_ready_draft_fallback",
        },
    )
    return hydrated


def main(email_sender=None, slack_sender=None) -> None:
    plan = hydrate_saved_draft_from_db(resolve_delivery_plan(load_input_plan()))
    if "customer" not in plan:
        print(json.dumps(missing_plan_result(plan, "missing_customer_plan")))
        return
    if "saved_draft" not in plan or not isinstance(plan.get("saved_draft"), dict):
        print(json.dumps(missing_plan_result(plan, "missing_saved_draft")))
        return
    runtime_job_id = plan.get("runtime_job_id")
    customer = plan["customer"]
    control_decision = plan.get("control_decision", {})
    saved_draft = plan.get("saved_draft")
    policy_decision = plan.get("policy_decision", {})
    delivery_settings = read_delivery_settings()
    brand = load_knowledge_section("brand")
    saved_draft = delivery_draft(plan, saved_draft, brand)
    test_recipient = (
        os.environ.get("SYNAPTIC_TEST_EMAIL_TO", "").strip()
        or str(delivery_settings.get("test_recipient", "")).strip()
    )
    actual_recipient = test_recipient or customer["email"]
    cycle = cycle_number(plan)
    quick_testing = quick_testing_enabled(delivery_settings)
    fast_test_sequence = bool(test_recipient)
    send_email = email_sender or (dry_run_email if quick_testing else post_email)
    send_slack = slack_sender or post_slack_message
    reply_context = dict(plan.get("reply_context") or {})
    email_headers = {"Idempotency-Key": saved_draft["draft_id"]}
    sent_email_copy = None
    thread_message_id = str(reply_context.get("thread_message_id") or "").strip()
    in_reply_to_message_id = str(
        reply_context.get("in_reply_to_message_id") or thread_message_id
    ).strip()
    references_message_ids = [
        str(item).strip()
        for item in list(reply_context.get("references_message_ids") or [])
        if str(item).strip()
    ]
    if in_reply_to_message_id:
        email_headers["In-Reply-To"] = in_reply_to_message_id
    if references_message_ids:
        email_headers["References"] = " ".join(references_message_ids)
    if thread_message_id and thread_message_id not in references_message_ids:
        email_headers["References"] = " ".join([*references_message_ids, thread_message_id]).strip()
        
    reserved_test_action_key: str | None = None

    if policy_decision.get("decision") == "block":
        delivery = {"status": "blocked", "reason": "deliverability_policy_block"}
        slack_delivery = {"status": "not_sent", "reason": "email_not_successful"}
    elif control_decision.get("decision") != "send_now":
        delivery = {
            "status": "waiting",
            "reason": "minimum_interval_not_reached",
            "scheduled_send_at": control_decision.get("scheduled_send_at"),
        }
        slack_delivery = {"status": "not_sent", "reason": "email_not_successful"}
    else:
        if test_recipient:
            reserved, reserved_test_action_key = reserve_test_delivery_action(
                test_recipient=test_recipient,
                plan=plan,
                saved_draft=saved_draft,
            )
            if not reserved:
                log_agent(
                    runtime_job_id,
                    AGENT_ID,
                    "Skipped duplicate test-mode campaign action.",
                    details={
                        "action_key": reserved_test_action_key,
                        "test_recipient": test_recipient,
                        "customer_id": customer.get("customer_id"),
                        "subject": saved_draft.get("subject"),
                    },
                )
                print(
                    json.dumps(
                        duplicate_test_action_result(
                            plan=plan,
                            saved_draft=saved_draft,
                            test_recipient=test_recipient,
                            action_key=reserved_test_action_key,
                        )
                    )
                )
                return

        execution_request = {
            "to": [actual_recipient],
            "subject": saved_draft["subject"],
            "text": saved_draft["body_text"],
            "html": saved_draft["html_body"],
            "headers": email_headers,
        }
        delivery = send_email(execution_request)
        if reserved_test_action_key is not None:
            complete_test_delivery_action(
                test_recipient=test_recipient,
                action_key=reserved_test_action_key,
                status=str(delivery.get("status") or "unknown"),
            )
        if delivery["status"] == "sent":
            sent_email_copy = safe_save_sent_email_copy(
                runtime_job_id=runtime_job_id,
                cycle=cycle,
                customer=customer,
                saved_draft=saved_draft,
                actual_recipient=actual_recipient,
                execution_request=execution_request,
                delivery=delivery,
                plan=plan,
            )
            mark_draft_sent(saved_draft["draft_id"], delivery.get("provider_id"))
            add_marketing_activity(
                customer["customer_id"],
                f"Sent email: {saved_draft['subject']}",
            )
            log_email_sent_event(runtime_job_id, actual_recipient, saved_draft["subject"])
            log_agent(
                runtime_job_id,
                AGENT_ID,
                "Sent email to customer.",
                details={
                    "customer_id": customer["customer_id"],
                    "provider_id": delivery.get("provider_id"),
                    "customer_email": customer["email"],
                    "delivery_recipient": actual_recipient,
                    "test_recipient_override": bool(test_recipient),
                    "subject": saved_draft["subject"],
                    "sent_email_copy": sent_email_copy,
                },
            )
        else:
            log_agent(
                runtime_job_id,
                AGENT_ID,
                "Email delivery failed.",
                details={
                    "customer_id": customer["customer_id"],
                    "customer_email": customer["email"],
                    "delivery_recipient": actual_recipient,
                    "test_recipient_override": bool(test_recipient),
                    "error": delivery.get("error"),
                    "subject": saved_draft["subject"],
                },
            )

    round_stats = record_round_delivery_attempt(
        runtime_job_id=runtime_job_id,
        cycle=cycle,
        customer_id=str(customer["customer_id"]),
        draft_id=str(saved_draft["draft_id"]),
        status=str(delivery.get("status") or "unknown"),
    )
    slack_delivery = safe_send_slack_round_report(
        send_slack,
        format_round_slack_report(
            round_stats=round_stats,
            customer=customer,
            actual_recipient=actual_recipient,
            status=str(delivery.get("status") or "unknown"),
        )
    )
    log_agent(
        runtime_job_id,
        AGENT_ID,
        "Reported email round delivery summary.",
        details={
            **round_stats,
            "slack_status": slack_delivery.get("status", "unknown"),
            "slack_channel": slack_delivery.get("channel"),
        },
    )

    print(
        json.dumps(
            {
                "events": [
                    {
                        "type": "email_delivery_attempted",
                        "payload": {
                            "customer_id": customer["customer_id"],
                            "email": actual_recipient,
                            "customer_email": customer["email"],
                            "subject": saved_draft["subject"],
                            "cycle": cycle,
                            "status": delivery["status"],
                            "http_status": delivery.get("http_status"),
                            "provider_id": delivery.get("provider_id"),
                            "reason": delivery.get("reason"),
                            "error": delivery.get("error"),
                            "dry_run": bool(delivery.get("dry_run")),
                            "quick_testing": quick_testing,
                            "test_recipient_override": bool(test_recipient),
                            "sent_email_copy": sent_email_copy,
                        },
                    },
                    *(
                        [
                            {
                                "type": "email_sent",
                                "payload": {
                                    "to": actual_recipient,
                                    "subject": saved_draft["subject"],
                                },
                            }
                        ]
                        if delivery["status"] == "sent"
                        else []
                    ),
                    {
                        "type": "slack_round_report_attempted",
                        "payload": {
                            "customer_id": customer["customer_id"],
                            "email": actual_recipient,
                            "customer_email": customer["email"],
                            "cycle": cycle,
                            "success_count": round_stats["success_count"],
                            "failed_count": round_stats["failed_count"],
                            "attempted_count": round_stats["attempted_count"],
                            "status": slack_delivery.get("status", "unknown"),
                            "channel": slack_delivery.get("channel", "#claw"),
                            "reason": slack_delivery.get("reason"),
                        },
                    },
                ],
                "emit_messages": [
                    *(
                        [
                            {
                                "to": "monitor_scheduler_agent",
                                "type": "cycle_trigger",
                                "body": {
                                    "status": delivery["status"],
                                    "cycle": cycle + 1,
                                    "original_plan": plan,
                                },
                                "class": "event",
                                "headers": {
                                    "schema_ref": "com.synaptic.monitor.cycle_trigger",
                                    "schema_version": "1.0.0",
                                },
                            }
                        ]
                        if should_emit_cycle_trigger(
                            delivery_status=delivery.get("status"),
                            cycle=cycle,
                            fast_test_sequence=fast_test_sequence,
                            campaign_type=plan.get("campaign_type"),
                        )
                        else []
                    )
                ],
                "next_state": {
                    "last_cycle": cycle,
                    "last_status": delivery["status"],
                    "last_round_delivery_report": round_stats,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
