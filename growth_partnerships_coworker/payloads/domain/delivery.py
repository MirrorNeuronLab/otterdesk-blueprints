from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from mn_email_delivery_skill import (
    SmtpDeliveryValidationError,
    SmtpSettings,
    send_smtp_email,
)
from mn_sdk.blueprint_support.workflow_state import write_json

from .inputs import json_object, normalized_inputs


DELIVERY_RECEIPT_PATH = "confidential_email_delivery_receipt.json"
ICLOUD_SMTP_HOST = "smtp.mail.me.com"
ICLOUD_SMTP_PORT = 587
SMTP_USERNAME_ENV = "MN_SMTP_USERNAME"
SMTP_PASSWORD_ENV = "MN_SMTP_PASSWORD"
SMTP_DEV_RECIPIENT_ENV = "MN_SMTP_DEV_RECIPIENT"
_APPROVAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def deliver_approved_development_email(
    context: dict[str, Any],
    queue: Mapping[str, Any],
    *,
    environment: Mapping[str, str] | None = None,
    smtp_sender: Callable[..., dict[str, Any]] = send_smtp_email,
) -> dict[str, Any]:
    """Deliver at most one approved development email and persist a safe receipt."""

    settings = (context.get("config") or {}).get("smtp_delivery") or {}
    if not bool(settings.get("enabled", False)):
        return _not_sent("smtp_delivery_disabled")
    if str(settings.get("mode") or "").strip().lower() != "development":
        raise RuntimeError("SMTP delivery supports development mode only")
    if int(settings.get("max_messages_per_run", 1)) != 1:
        raise RuntimeError("Development SMTP delivery must be limited to one message per run")

    approval = normalized_inputs(context).get("email_send_approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return _not_sent("explicit_approval_required")
    approval_id = str(approval.get("approval_id") or "").strip()
    if not _APPROVAL_ID_PATTERN.fullmatch(approval_id):
        raise RuntimeError("Approved SMTP delivery requires a bounded approval_id")

    smtp_host = str(settings.get("host") or "").strip().lower()
    security = str(settings.get("security") or "").strip().lower()
    try:
        smtp_port = int(settings.get("port"))
        timeout_seconds = float(settings.get("timeout_seconds", 10))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("SMTP delivery configuration is invalid") from exc
    if (smtp_host, smtp_port, security) != (
        ICLOUD_SMTP_HOST,
        ICLOUD_SMTP_PORT,
        "starttls",
    ):
        raise RuntimeError("SMTP delivery must use the approved iCloud STARTTLS endpoint")

    env = environment if environment is not None else os.environ
    username = str(env.get(SMTP_USERNAME_ENV) or "").strip()
    password = str(env.get(SMTP_PASSWORD_ENV) or "")
    development_recipient = str(env.get(SMTP_DEV_RECIPIENT_ENV) or "").strip()
    if not username or not password or not development_recipient:
        raise RuntimeError(
            "SMTP delivery credentials and the development recipient must be injected through the worker environment"
        )

    draft = _first_approved_draft(queue)
    request = {
        "to": [development_recipient],
        "subject": _development_subject(draft["subject"]),
        "text": _development_body(draft["body"]),
    }
    delivery_key = hashlib.sha256(
        "\x1f".join(
            (
                approval_id,
                development_recipient.lower(),
                request["subject"],
                request["text"],
            )
        ).encode("utf-8")
    ).hexdigest()
    approval_ref = hashlib.sha256(approval_id.encode("utf-8")).hexdigest()[:16]
    receipt_path = Path(context["run_dir"]) / DELIVERY_RECEIPT_PATH
    existing = json_object(receipt_path)
    if existing:
        if existing.get("delivery_key") == delivery_key and existing.get("status") == "sent":
            return {
                "status": "already_sent",
                "reason": "idempotent_replay",
                "mode": "development",
                "recipient_count": 1,
                "message_id": str(existing.get("message_id") or ""),
                "receipt_artifact": DELIVERY_RECEIPT_PATH,
            }
        raise RuntimeError("A prior SMTP attempt exists for this run; start a new reviewed run")

    receipt = {
        "schema_version": "mn.business_growth.email_delivery_receipt.v1",
        "classification": "confidential_delivery_metadata",
        "status": "sending",
        "mode": "development",
        "recipient_policy": "environment_injected_single_test_recipient",
        "recipient_count": 1,
        "approval_ref": approval_ref,
        "delivery_key": delivery_key,
        "smtp_host": smtp_host,
        "started_at": str(context.get("started_at") or "not_reported"),
    }
    write_json(receipt_path, receipt)
    try:
        result = smtp_sender(
            request,
            settings=SmtpSettings(
                host=smtp_host,
                port=smtp_port,
                username=username,
                password=password,
                from_address=username,
                security="starttls",
                timeout_seconds=timeout_seconds,
            ),
            allowed_hosts=[ICLOUD_SMTP_HOST],
            idempotency_key=delivery_key,
        )
    except SmtpDeliveryValidationError as exc:
        write_json(receipt_path, {**receipt, "status": "failed", "reason": "smtp_request_rejected"})
        raise RuntimeError("SMTP delivery request failed validation") from exc

    if result.get("status") != "sent":
        write_json(
            receipt_path,
            {
                **receipt,
                "status": "failed",
                "reason": str(result.get("reason") or "smtp_delivery_failed"),
            },
        )
        raise RuntimeError("SMTP delivery did not complete")

    safe_result = {
        "status": "sent",
        "mode": "development",
        "recipient_count": 1,
        "message_id": str(result.get("message_id") or ""),
        "receipt_artifact": DELIVERY_RECEIPT_PATH,
    }
    write_json(receipt_path, {**receipt, **safe_result})
    return safe_result


def _first_approved_draft(queue: Mapping[str, Any]) -> dict[str, str]:
    contacts = queue.get("contacts")
    if not isinstance(contacts, list):
        raise RuntimeError("The confidential outreach queue is missing")
    for contact in contacts:
        if not isinstance(contact, dict) or not (contact.get("draft_review") or {}).get("approved"):
            continue
        draft = contact.get("draft")
        if not isinstance(draft, dict):
            continue
        subject = str(draft.get("subject") or "").strip()
        body = str(draft.get("body") or "").strip()
        if subject and body:
            return {"subject": subject, "body": body}
    raise RuntimeError("No quality-approved outreach draft is available")


def _development_subject(subject: str) -> str:
    prefix = "[Development test] "
    return f"{prefix}{subject}"[:200]


def _development_body(body: str) -> str:
    anonymized = re.sub(r"\AHi[^\r\n]*", "Hi there", body, count=1)
    return (
        "Development delivery test only. The queued contact address was not used.\n\n"
        f"{anonymized}"
    )


def _not_sent(reason: str) -> dict[str, Any]:
    return {
        "status": "not_sent",
        "reason": reason,
        "mode": "development",
        "recipient_count": 0,
        "receipt_artifact": "",
    }


__all__ = [
    "DELIVERY_RECEIPT_PATH",
    "ICLOUD_SMTP_HOST",
    "ICLOUD_SMTP_PORT",
    "SMTP_DEV_RECIPIENT_ENV",
    "SMTP_PASSWORD_ENV",
    "SMTP_USERNAME_ENV",
    "deliver_approved_development_email",
]
