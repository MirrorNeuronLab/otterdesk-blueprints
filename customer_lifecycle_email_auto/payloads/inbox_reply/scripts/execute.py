#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger("mn.blueprint.business_email.inbox_reply")

payload_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(payload_root))
vendored_skills = Path(__file__).resolve().parents[1] / "mn_skills"
if vendored_skills.exists():
    sys.path.insert(0, str(vendored_skills))
shared_skills = Path(__file__).resolve().parents[2] / "_shared_skills"
if shared_skills.exists():
    sys.path.insert(0, str(shared_skills))


def load_local_env() -> None:
    for env_path in (
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[1] / "mn_skills" / ".env",
    ):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


load_local_env()

try:
    from mn_email_receive_agentmail_skill import AgentMailReceiveConfig
    from mn_email_receive_agentmail_skill import get_message as skill_get_message
    from mn_email_receive_agentmail_skill import list_unread_messages as skill_list_unread_messages
    from mn_email_receive_agentmail_skill import mark_read as skill_mark_read
    from mn_email_receive_agentmail_skill import send_reply as skill_send_reply
    from mn_email_send_resend_skill import send_resend_email as skill_send_resend_email
except ImportError:
    AgentMailReceiveConfig = None
    skill_get_message = None
    skill_list_unread_messages = None
    skill_mark_read = None
    skill_send_reply = None
    skill_send_resend_email = None

try:
    from business_email_campaign_skill import build_design_slots, render_email_html
    from mn_email_delivery_skill import post_slack_message
except ImportError:
    build_design_slots = None
    render_email_html = None
    post_slack_message = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_artifact_slug(value: object, fallback: str = "email") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-")
    return slug[:80] or fallback


def sent_email_copy_root(runtime_job_id: str | None = None) -> Path:
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
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    delivery: dict,
    source: str,
) -> dict:
    root = sent_email_copy_root(runtime_job_id)
    email_dir = root / "sent_emails"
    email_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now()
    prefix = "-".join(
        [
            timestamp.replace("-", "").replace(":", "").replace("+00:00", "Z"),
            "inbox-reply",
            safe_artifact_slug(to_email, "recipient"),
            str(time.time_ns()),
        ]
    )
    html_path = email_dir / f"{prefix}.html"
    text_path = email_dir / f"{prefix}.txt"
    metadata_path = email_dir / f"{prefix}.json"
    html_path.write_text(str(html_body or ""), encoding="utf-8")
    text_path.write_text(str(text_body or ""), encoding="utf-8")
    metadata = {
        "timestamp": timestamp,
        "runtime_job_id": runtime_job_id,
        "agent_id": "inbox_reply_agent",
        "source": source,
        "recipient": to_email,
        "subject": f"Re: {subject}",
        "delivery_status": delivery.get("status"),
        "provider": delivery.get("provider"),
        "provider_id": delivery.get("provider_id"),
        "html_path": str(html_path),
        "text_path": str(text_path),
        "has_card_email_marker": "Story moments to explore" in str(html_body or ""),
        "has_personal_reply_marker": (
            "data-slot=\"body_section\"" in str(html_body or "")
            and "Story moments to explore" not in str(html_body or "")
        ),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "saved",
        "root": str(root),
        "html_path": str(html_path),
        "text_path": str(text_path),
        "metadata_path": str(metadata_path),
        "html_content": str(html_body or ""),
        "text_content": str(text_body or ""),
        "metadata": metadata,
    }


def safe_save_sent_email_copy(**kwargs) -> dict:
    try:
        return save_sent_email_copy(**kwargs)
    except Exception as exc:
        return {"status": "failed", "reason": "sent_email_copy_error", "error": str(exc)}


def load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def payload_input_dir() -> Path:
    payload_input = Path(__file__).resolve().parents[1] / "input"
    if payload_input.exists():
        return payload_input
    return Path(__file__).resolve().parents[3] / "input"


def blueprint_root_dir() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "knowledge").is_dir():
            return parent
        if (parent / "config").is_dir() and (parent / "payloads").is_dir():
            return parent
    return current.parents[3]


def load_knowledge() -> dict:
    knowledge = load_json_file(blueprint_root_dir() / "knowledge" / "init" / "knowledge.json")
    if knowledge:
        return knowledge
    return load_json_file(payload_input_dir() / "knowledge.json")


def load_brand() -> dict:
    knowledge = load_knowledge()
    brand = knowledge.get("brand", {})
    return brand if isinstance(brand, dict) else {}


def load_template(template_id: str) -> dict:
    template = load_json_file(payload_input_dir() / "templates" / f"{template_id}.json")
    return template if template.get("template_id") else {}


def render_reply_html(*, subject: str, reply_text: str, inbound_body: str = "") -> str:
    if build_design_slots is None or render_email_html is None:
        return ""
    brand = load_brand()
    template = load_template("personal_reply")
    if not template:
        return ""
    body_sections = [reply_text.strip() or "Thank you for your message. We have received it."]
    plan = {
        "campaign_type": "reply_followup",
        "audience_segment": "inbound_reply",
        "primary_offer": "Bibblio",
        "goal": "Reply to an inbound message",
        "reply_context": {"subject": subject, "text_body": inbound_body},
        "customer": {
            "customer_id": "inbound_reply",
            "name": "there",
            "email": "",
        },
        "draft": {
            "subject": f"Re: {subject}",
            "preview_text": "A quick personal reply from Bibblio.",
            "eyebrow": "Thanks for writing",
            "headline": "A quick note back from Bibblio",
            "body_sections": body_sections,
            "cta_label": "Visit Bibblio",
            "cta_url_slug": "discover",
            "secondary_text": "You can reply here with any other details and we will keep helping.",
            "footer_variant": "reply",
            "signoff": brand.get("signoff_name", "Maya"),
        },
    }
    slots = build_design_slots(plan=plan, brand=brand)
    return render_email_html(template, slots)


def send_slack_reply_report(*, to_email: str, subject: str, delivery: dict) -> dict:
    if post_slack_message is None:
        return {"status": "skipped", "reason": "slack_skill_unavailable"}
    status = str(delivery.get("status") or "unknown")
    message = (
        f"Business email inbox reply report: reply to <{to_email}> was {status}. "
        f"Subject: Re: {subject}"
    )
    try:
        return post_slack_message(message) or {}
    except Exception as exc:
        return {"status": "failed", "reason": "slack_report_error", "error": str(exc)}

def log_customer_reply(from_email: str, body: str):
    db_path = "/tmp/mn_business_email_campaign.db"
    if not os.path.exists(db_path):
        return
    
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_marketing_activity (
                activity_id TEXT PRIMARY KEY,
                customer_id TEXT,
                summary TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_drafts (
                draft_id TEXT PRIMARY KEY,
                customer_id TEXT,
                runtime_job_id TEXT,
                status TEXT,
                subject TEXT,
                preview_text TEXT,
                body_text TEXT,
                html_body TEXT,
                scheduled_send_at TEXT,
                prepared_at TEXT,
                provider_id TEXT,
                sent_at TEXT,
                from_email TEXT,
                thread_message_id TEXT,
                in_reply_to_message_id TEXT,
                references_message_ids_json TEXT,
                source_payload_json TEXT
            )
            """
        )
        
        # Determine the customer id loosely based on the email we received
        if "davis" in from_email.lower():
            customer_id = "cust_mr_davis_teacher"
        elif "ava" in from_email.lower() or "martinez" in from_email.lower():
            customer_id = "cust_ava_repeat_creator"
        else:
            # Fallback to the last customer we emailed if we're testing via override
            row = conn.execute("SELECT customer_id FROM email_drafts WHERE status = 'sent' ORDER BY sent_at DESC LIMIT 1").fetchone()
            customer_id = row["customer_id"] if row else "cust_maya_new_parent"
            
        activity_id = f"activity_{utc_now().replace('-', '').replace(':', '').replace('+00:00', 'z').lower()}"
        summary = f"Customer replied: {body[:200]}"
        conn.execute(
            """
            INSERT INTO customer_marketing_activity (
                activity_id,
                customer_id,
                summary,
                created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (activity_id, customer_id, summary, utc_now()),
        )
        conn.commit()
        logger.info("Logged reply activity for customer: %s", customer_id)
        conn.close()
    except Exception as e:
        logger.exception("Error logging reply to db")


def generate_reply_via_llm(body_content):
    try:
        from mn_litellm_communicate_skill import completion_text

        return completion_text(
            "You are a warm, helpful customer support representative for Bibblio, "
            "a company that makes personalized children's SEL (social-emotional learning) "
            "picture books. Keep your response friendly but concise (1-3 sentences max).",
            f"Customer email body:\n{body_content}",
            fallback="Thank you for your message. We have received it.",
        )
    except Exception:
        logger.exception("Error calling LLM")
        return "Thank you for your message. We have received it."

def agentmail_request(method: str, path: str, body: dict | None = None, query: dict | None = None) -> dict:
    api_key = os.environ.get("AGENTMAIL_API_KEY")
    if not api_key:
        return {}
    url = "https://api.agentmail.to" + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def check_agentmail() -> list:
    api_key = os.environ.get("AGENTMAIL_API_KEY")
    inbox_id = os.environ.get("AGENTMAIL_INBOX")
    if not api_key or not inbox_id:
        return []

    if (
        AgentMailReceiveConfig is not None
        and skill_get_message is not None
        and skill_list_unread_messages is not None
        and skill_mark_read is not None
        and skill_send_reply is not None
    ):
        return check_agentmail_with_skill()

    processed = []
    inbox_path = urllib.parse.quote(inbox_id, safe="")
    try:
        res = agentmail_request(
            "GET",
            f"/v0/inboxes/{inbox_path}/messages",
            query={"labels": ["unread"]},
        )
        messages = res.get("messages") or res.get("data") or []
        
        for msg in messages:
            subject = msg.get("subject") or ""
            
            # Respond to ALL incoming emails now
            from_email = msg.get("from") or msg.get("from_") or ""
            if not from_email:
                continue
                
            if "<" in from_email and ">" in from_email:
                from_email = from_email.split("<")[1].split(">")[0]
                
            if inbox_id in from_email:
                # Skip processing our own emails to prevent loops
                agentmail_request(
                    "PATCH",
                    f"/v0/inboxes/{inbox_path}/messages/{urllib.parse.quote(str(msg.get('message_id') or msg.get('id')), safe='')}",
                    body={"add_labels": ["read"], "remove_labels": ["unread"]},
                )
                continue
                
            # Fetch the full message to get the actual body content
            message_id = str(msg.get("message_id") or msg.get("id"))
            full_msg = agentmail_request(
                "GET",
                f"/v0/inboxes/{inbox_path}/messages/{urllib.parse.quote(message_id, safe='')}",
            )
            body = (
                full_msg.get("extracted_text")
                or full_msg.get("text")
                or msg.get("extracted_text")
                or msg.get("text")
                or "No content provided."
            )
            logger.info("Processing email from %s", from_email)
            
            log_customer_reply(from_email, body)
            reply_text = generate_reply_via_llm(body)
            reply_html = render_reply_html(
                subject=subject,
                reply_text=reply_text,
                inbound_body=body,
            )
            
            agentmail_request(
                "POST",
                f"/v0/inboxes/{inbox_path}/messages/send",
                body={
                    "to": from_email,
                    "subject": f"Re: {subject}",
                    "text": reply_text,
                    "html": reply_html or None,
                },
            )
            reply_delivery = {"status": "sent", "provider": "agentmail"}
            sent_email_copy = safe_save_sent_email_copy(
                runtime_job_id=os.environ.get("MN_JOB_ID") or os.environ.get("SYNAPTIC_JOB_ID"),
                to_email=from_email,
                subject=subject,
                text_body=reply_text,
                html_body=reply_html,
                delivery=reply_delivery,
                source="inbox_reply_agentmail",
            )
            slack_delivery = send_slack_reply_report(
                to_email=from_email,
                subject=subject,
                delivery=reply_delivery,
            )
            # Mark as read so we don't process it again
            agentmail_request(
                "PATCH",
                f"/v0/inboxes/{inbox_path}/messages/{urllib.parse.quote(message_id, safe='')}",
                body={"add_labels": ["read"], "remove_labels": ["unread"]},
            )
            processed.append({
                "type": "agent_inbox_email_received",
                "payload": {
                    "from": from_email,
                    "subject": subject,
                    "body": body[:500]
                }
            })
            processed.append({
                "type": "agent_inbox_reply_sent",
                "payload": {
                    "to": from_email,
                    "subject": f"Re: {subject}",
                    "reply_text": reply_text,
                    "html_template": "personal_reply" if reply_html else None,
                    "delivery": reply_delivery,
                    "slack": slack_delivery,
                    "sent_email_copy": sent_email_copy,
                }
            })
            
    except Exception as e:
        logger.exception("AgentMail fetch/reply error")
    return processed


def check_agentmail_with_skill() -> list:
    config = AgentMailReceiveConfig.from_env()
    processed = []
    try:
        for msg in skill_list_unread_messages(config):
            subject = msg.subject or ""
            from_email = msg.from_email
            if not from_email:
                continue
            if "<" in from_email and ">" in from_email:
                from_email = from_email.split("<")[1].split(">")[0]
            if config.inbox_id in from_email:
                skill_mark_read(msg.message_id, config)
                continue

            full_msg = skill_get_message(msg.message_id, config)
            body = full_msg.extracted_text or full_msg.text or msg.extracted_text or msg.text or "No content provided."
            logger.info("Processing email from %s", from_email)
            log_customer_reply(from_email, body)
            processed.append({
                "type": "agent_inbox_email_received",
                "payload": {
                    "from": from_email,
                    "subject": subject,
                    "body": body[:500]
                }
            })
            reply_text = generate_reply_via_llm(body)
            reply_html = render_reply_html(
                subject=subject,
                reply_text=reply_text,
                inbound_body=body,
            )
            reply_delivery = {"status": "not_sent"}
            try:
                agentmail_request(
                    "POST",
                    f"/v0/inboxes/{urllib.parse.quote(config.inbox_id, safe='')}/messages/send",
                    body={
                        "to": from_email,
                        "subject": f"Re: {subject}",
                        "text": reply_text,
                        "html": reply_html or None,
                    },
                )
                reply_delivery = {"status": "sent", "provider": "agentmail"}
            except Exception as exc:
                if skill_send_resend_email is not None:
                    resend_result = skill_send_resend_email({
                        "to": [from_email],
                        "subject": f"Re: {subject}",
                        "text": reply_text,
                        "html": reply_html or None,
                    })
                    reply_delivery = {
                        "status": resend_result.get("status"),
                        "provider": "resend",
                        "provider_id": resend_result.get("provider_id"),
                        "error": resend_result.get("error"),
                    }
                else:
                    reply_delivery = {
                        "status": "failed",
                        "provider": "agentmail",
                        "error": str(exc),
                    }
            finally:
                skill_mark_read(msg.message_id, config)
            slack_delivery = send_slack_reply_report(
                to_email=from_email,
                subject=subject,
                delivery=reply_delivery,
            )
            sent_email_copy = (
                safe_save_sent_email_copy(
                    runtime_job_id=os.environ.get("MN_JOB_ID")
                    or os.environ.get("SYNAPTIC_JOB_ID"),
                    to_email=from_email,
                    subject=subject,
                    text_body=reply_text,
                    html_body=reply_html,
                    delivery=reply_delivery,
                    source="inbox_reply_skill",
                )
                if reply_delivery.get("status") == "sent"
                else None
            )
            processed.append({
                "type": "agent_inbox_reply_sent",
                "payload": {
                    "to": from_email,
                    "subject": f"Re: {subject}",
                    "reply_text": reply_text,
                    "html_template": "personal_reply" if reply_html else None,
                    "delivery": reply_delivery,
                    "slack": slack_delivery,
                    "sent_email_copy": sent_email_copy,
                }
            })
    except Exception as e:
        logger.exception("AgentMail fetch/reply error")
    return processed

def main():
    processed = check_agentmail()
    if processed:
        print(json.dumps({"events": processed}))
    else:
        print(json.dumps({"events": []}))

if __name__ == "__main__":
    main()
