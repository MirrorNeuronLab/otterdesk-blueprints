from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
for source in sorted((WORKSPACE / "mn-skills").glob("*/src")):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


def _load_delivery():
    payloads = ROOT / "growth_partnerships_coworker" / "payloads"
    for module_name in [name for name in sys.modules if name == "domain" or name.startswith("domain.")]:
        sys.modules.pop(module_name)
    if str(payloads) not in sys.path:
        sys.path.insert(0, str(payloads))
    return importlib.import_module("domain.delivery")


def _context(tmp_path: Path, *, enabled: bool = True, approved: bool = True) -> dict:
    approval = {"approved": approved}
    if approved:
        approval["approval_id"] = "founder-review-001"
    return {
        "run_dir": str(tmp_path),
        "started_at": "2026-08-03T12:00:00Z",
        "config": {
            "inputs": {"payload": {"email_send_approval": approval}},
            "smtp_delivery": {
                "enabled": enabled,
                "mode": "development",
                "host": "smtp.mail.me.com",
                "port": 587,
                "security": "starttls",
                "timeout_seconds": 10,
                "max_messages_per_run": 1,
            },
        },
    }


def _queue() -> dict:
    return {
        "contacts": [
            {
                "name": "Queued Person",
                "email": "queued-person@example.invalid",
                "draft_review": {"approved": True},
                "draft": {
                    "subject": "A focused conversation",
                    "body": "Hi Queued\n\nHere is a useful product conversation.",
                },
            },
            {
                "name": "Second Person",
                "email": "second-person@example.invalid",
                "draft_review": {"approved": True},
                "draft": {"subject": "Second", "body": "Hi Second\n\nSecond body."},
            },
        ]
    }


def _environment() -> dict[str, str]:
    return {
        "MN_SMTP_USERNAME": "sender@example.invalid",
        "MN_SMTP_PASSWORD": "fake-app-password",
        "MN_SMTP_DEV_RECIPIENT": "dev-recipient@example.invalid",
    }


def test_development_delivery_sends_exactly_one_anonymized_message_to_test_recipient(tmp_path):
    delivery = _load_delivery()
    calls = []

    def fake_sender(request, **kwargs):
        calls.append((request, kwargs))
        return {
            "status": "sent",
            "provider": "smtp",
            "message_id": "<test-message@mirrorneuron.local>",
            "recipient_count": 1,
        }

    result = delivery.deliver_approved_development_email(
        _context(tmp_path),
        _queue(),
        environment=_environment(),
        smtp_sender=fake_sender,
    )

    assert result == {
        "status": "sent",
        "mode": "development",
        "recipient_count": 1,
        "message_id": "<test-message@mirrorneuron.local>",
        "receipt_artifact": "confidential_email_delivery_receipt.json",
    }
    assert len(calls) == 1
    request, options = calls[0]
    assert request["to"] == ["dev-recipient@example.invalid"]
    assert request["subject"].startswith("[Development test]")
    assert request["text"].startswith("Development delivery test only.")
    assert "Hi there" in request["text"]
    assert "Queued" not in request["text"]
    assert "queued-person@example.invalid" not in repr(request)
    assert "second-person@example.invalid" not in repr(request)
    assert options["allowed_hosts"] == ["smtp.mail.me.com"]
    assert options["settings"].host == "smtp.mail.me.com"
    assert options["settings"].port == 587
    assert options["settings"].security == "starttls"
    assert options["settings"].username == "sender@example.invalid"

    receipt_text = (tmp_path / delivery.DELIVERY_RECEIPT_PATH).read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["status"] == "sent"
    assert receipt["recipient_count"] == 1
    for private_value in (
        "fake-app-password",
        "sender@example.invalid",
        "dev-recipient@example.invalid",
        "queued-person@example.invalid",
        "founder-review-001",
    ):
        assert private_value not in receipt_text


def test_completed_delivery_replay_does_not_open_a_second_smtp_transaction(tmp_path):
    delivery = _load_delivery()
    calls = 0

    def fake_sender(_request, **_kwargs):
        nonlocal calls
        calls += 1
        return {"status": "sent", "message_id": "<stable@mirrorneuron.local>"}

    first = delivery.deliver_approved_development_email(
        _context(tmp_path),
        _queue(),
        environment=_environment(),
        smtp_sender=fake_sender,
    )
    second = delivery.deliver_approved_development_email(
        _context(tmp_path),
        _queue(),
        environment=_environment(),
        smtp_sender=fake_sender,
    )

    assert first["status"] == "sent"
    assert second["status"] == "already_sent"
    assert second["reason"] == "idempotent_replay"
    assert calls == 1


@pytest.mark.parametrize(
    ("enabled", "approved", "reason"),
    [
        (False, True, "smtp_delivery_disabled"),
        (True, False, "explicit_approval_required"),
    ],
)
def test_disabled_or_unapproved_delivery_never_calls_smtp(tmp_path, enabled, approved, reason):
    delivery = _load_delivery()

    def forbidden_sender(*_args, **_kwargs):
        raise AssertionError("SMTP must not be called")

    result = delivery.deliver_approved_development_email(
        _context(tmp_path, enabled=enabled, approved=approved),
        _queue(),
        environment=_environment(),
        smtp_sender=forbidden_sender,
    )

    assert result["status"] == "not_sent"
    assert result["reason"] == reason
    assert not (tmp_path / delivery.DELIVERY_RECEIPT_PATH).exists()


def test_development_delivery_requires_secret_environment_before_reserving_send(tmp_path):
    delivery = _load_delivery()

    with pytest.raises(RuntimeError, match="injected through the worker environment"):
        delivery.deliver_approved_development_email(
            _context(tmp_path),
            _queue(),
            environment={},
        )

    assert not (tmp_path / delivery.DELIVERY_RECEIPT_PATH).exists()


def test_development_delivery_rejects_more_than_one_message_per_run(tmp_path):
    delivery = _load_delivery()
    context = _context(tmp_path)
    context["config"]["smtp_delivery"]["max_messages_per_run"] = 2

    with pytest.raises(RuntimeError, match="limited to one message"):
        delivery.deliver_approved_development_email(
            context,
            _queue(),
            environment=_environment(),
        )
