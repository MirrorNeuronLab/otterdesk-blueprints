from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from workspace_paths import companion_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
for source in sorted((WORKSPACE / "mn-skills").glob("*/src")):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


def _load_delivery():
    payloads = ROOT / "gtm_assistant" / "payloads"
    for module_name in [name for name in sys.modules if name == "domain" or name.startswith("domain.")]:
        sys.modules.pop(module_name)
    if str(payloads) not in sys.path:
        sys.path.insert(0, str(payloads))
    return importlib.import_module("domain.delivery")


def _context(tmp_path: Path, *, enabled: bool = True, approved: bool = True) -> dict:
    approval = {"approved": approved}
    if approved:
        approval["approval_id"] = "founder-review-gtm-001"
    return {
        "run_dir": str(tmp_path),
        "started_at": "2026-08-10T12:00:00Z",
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


def _interventions() -> list[dict]:
    return [
        {
            "draft_review": {"approved": True},
            "draft": {
                "subject": "A simple next step",
                "preview_text": "A small continuation without pressure.",
                "body_sections": [
                    {"title": "What we noticed", "body": "Some customers found setup difficult."},
                    {"title": "A small next step", "body": "Try one relevant next activity."},
                ],
                "cta_label": "Review the next activity",
                "footer": "Draft only — do not send without approval.",
            },
        }
    ]


def _environment() -> dict[str, str]:
    return {
        "MN_SMTP_USERNAME": "sender@example.invalid",
        "MN_SMTP_PASSWORD": "fake-app-password",
        "MN_SMTP_DEV_RECIPIENT": "dev-recipient@example.invalid",
    }


def test_development_delivery_sends_one_anonymized_message_to_the_injected_test_recipient(tmp_path):
    delivery = _load_delivery()
    calls = []

    def fake_sender(request, **kwargs):
        calls.append((request, kwargs))
        return {"status": "sent", "provider": "smtp", "message_id": "<test@mirrorneuron.local>"}

    result = delivery.deliver_approved_development_email(
        _context(tmp_path),
        _interventions(),
        environment=_environment(),
        smtp_sender=fake_sender,
    )

    assert result == {
        "status": "sent",
        "mode": "development",
        "recipient_count": 1,
        "message_id": "<test@mirrorneuron.local>",
        "receipt_artifact": "confidential_lifecycle_email_delivery_receipt.json",
    }
    assert len(calls) == 1
    request, options = calls[0]
    assert request["to"] == ["dev-recipient@example.invalid"]
    assert request["subject"].startswith("[Development test]")
    assert request["text"].startswith("Development delivery test only.")
    assert "Hi there" in request["text"]
    assert "sender@example.invalid" not in repr(request)
    assert "dev-recipient@example.invalid" not in (tmp_path / delivery.DELIVERY_RECEIPT_PATH).read_text(encoding="utf-8")
    assert options["allowed_hosts"] == ["smtp.mail.me.com"]
    assert options["settings"].security == "starttls"


def test_delivery_is_disabled_by_default_and_requires_explicit_approval(tmp_path):
    delivery = _load_delivery()

    def forbidden_sender(*_args, **_kwargs):
        raise AssertionError("SMTP must not be called")

    assert delivery.deliver_approved_development_email(
        _context(tmp_path, enabled=False), _interventions(), environment=_environment(), smtp_sender=forbidden_sender
    )["reason"] == "smtp_delivery_disabled"
    assert delivery.deliver_approved_development_email(
        _context(tmp_path, approved=False), _interventions(), environment=_environment(), smtp_sender=forbidden_sender
    )["reason"] == "explicit_approval_required"


def test_enabled_delivery_creates_one_runtime_human_approval_request(tmp_path):
    delivery = _load_delivery()
    run_id = "gtm-human-approval-test"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    context = _context(run_dir, approved=False)
    context["run_id"] = run_id

    first = delivery.request_development_email_approval(context)
    second = delivery.request_development_email_approval(context)

    assert first["type"] == "human_input_requested"
    assert first["payload"] == {
        "request_id": f"gtm-development-email:{run_id}",
        "prompt": "Send one aggregate development email to the configured test recipient?",
        "options": ["Approve", "Reject"],
        "allowed_decisions": ["approve", "reject"],
        "decision_type": "external_email_send",
        "action": "send_development_email",
        "status": "pending",
    }
    assert second is None
    events = [json.loads(line) for line in (run_dir / "human.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1

    with (run_dir / "human.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "type": "human_input_received",
            "payload": {
                "request_id": f"gtm-development-email:{run_id}",
                "decision": "approve",
                "approved": True,
            },
        }) + "\n")

    assert delivery.development_email_approval_response(context)["approved"] is True


def test_delivery_replay_does_not_open_a_second_smtp_transaction(tmp_path):
    delivery = _load_delivery()
    calls = 0

    def fake_sender(_request, **_kwargs):
        nonlocal calls
        calls += 1
        return {"status": "sent", "message_id": "<stable@mirrorneuron.local>"}

    first = delivery.deliver_approved_development_email(_context(tmp_path), _interventions(), environment=_environment(), smtp_sender=fake_sender)
    second = delivery.deliver_approved_development_email(_context(tmp_path), _interventions(), environment=_environment(), smtp_sender=fake_sender)

    assert first["status"] == "sent"
    assert second["status"] == "already_sent"
    assert calls == 1


def test_default_config_keeps_smtp_disabled_without_live_identity_or_secret():
    config_text = (ROOT / "gtm_assistant" / "config" / "default.json").read_text(encoding="utf-8")
    manifest_text = (ROOT / "gtm_assistant" / "manifest.json").read_text(encoding="utf-8")
    config = json.loads(config_text)

    assert config["smtp_delivery"]["enabled"] is False
    assert config["inputs"]["payload"]["email_send_approval"] == {"approved": False}
    assert config["reply_monitoring"] == {
        "enabled": False,
        "host": "imap.mail.me.com",
        "port": 993,
        "security": "ssl",
        "timeout_seconds": 10,
        "poll_interval_seconds": 15,
    }
    assert "@me.com" not in config_text
    assert "@gmail.com" not in config_text
    assert "@me.com" not in manifest_text
    assert "@gmail.com" not in manifest_text


def test_manifest_declares_separate_otterdesk_smtp_fields_without_live_values():
    manifest = json.loads((ROOT / "gtm_assistant" / "manifest.json").read_text(encoding="utf-8"))
    review = manifest["metadata"]["init_config_review"]
    fields = {field["path"]: field for field in review["fields"]}

    assert review["required"] is True
    assert fields["smtp_delivery.enabled"]["default"] is False
    assert fields["smtp_delivery.host"]["default"] == "smtp.mail.me.com"
    assert fields["smtp_delivery.port"]["default"] == "587"
    assert fields["smtp_delivery.security"]["default"] == "starttls"
    assert fields["smtp_credentials.username"]["environment_variable"] == "MN_SMTP_USERNAME"
    assert fields["smtp_credentials.app_password"] == {
        "path": "smtp_credentials.app_password",
        "label": "App-Specific Password",
        "type": "password",
        "default": "",
        "required": True,
        "secret": True,
        "active_when_any": [
            {"path": "smtp_delivery.enabled", "equals": True},
            {"path": "reply_monitoring.enabled", "equals": True},
        ],
        "environment_variable": "MN_SMTP_PASSWORD",
        "description": "An Apple app-specific password. It is encrypted in the OS credential store and never saved in the co-worker registry or configuration JSON.",
    }
    assert fields["smtp_credentials.development_recipient"]["environment_variable"] == "MN_SMTP_DEV_RECIPIENT"
    assert fields["reply_monitoring.enabled"]["default"] is False
    assert fields["inputs.payload.email_send_approval.approved"]["default"] is False


def test_mcp_collaboration_service_is_safe_to_restart_after_local_core_recovery():
    manifest = json.loads((ROOT / "gtm_assistant" / "manifest.json").read_text(encoding="utf-8"))
    mcp_server = next(
        node
        for node in manifest["agents"]["extra_nodes"]
        if node["node_id"] == "mcp_collaboration_server"
    )

    assert mcp_server["config"]["idempotent"] is True
    assert mcp_server["config"]["safe_to_retry"] is True


def test_delivery_rejects_more_than_one_message_per_run(tmp_path):
    delivery = _load_delivery()
    context = _context(tmp_path)
    context["config"]["smtp_delivery"]["max_messages_per_run"] = 2

    with pytest.raises(RuntimeError, match="limited to one message"):
        delivery.deliver_approved_development_email(context, _interventions(), environment=_environment())
