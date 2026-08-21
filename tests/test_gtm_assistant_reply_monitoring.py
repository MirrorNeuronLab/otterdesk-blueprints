from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path

from workspace_paths import companion_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
for source in sorted((WORKSPACE / "mn-skills").glob("*/src")):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


def _load_monitoring():
    payloads = ROOT / "gtm_assistant" / "payloads"
    for module_name in [name for name in sys.modules if name == "domain" or name.startswith("domain.")]:
        sys.modules.pop(module_name)
    if str(payloads) not in sys.path:
        sys.path.insert(0, str(payloads))
    return importlib.import_module("domain.reply_monitoring")


class _FakeImap:
    def __init__(self, headers_by_message: dict[bytes, bytes]):
        self.headers_by_message = headers_by_message
        self.readonly = False
        self.logged_out = False

    def login(self, _username, _password):
        return "OK", [b"logged in"]

    def select(self, _mailbox, readonly=False):
        self.readonly = readonly
        return "OK", [str(len(self.headers_by_message)).encode("ascii")]

    def search(self, _charset, _query):
        return "OK", [b" ".join(self.headers_by_message)]

    def fetch(self, message_number, _query):
        return "OK", [(b"headers", self.headers_by_message[message_number])]

    def logout(self):
        self.logged_out = True
        return "BYE", [b"logged out"]


def _settings() -> dict:
    return {
        "host": "imap.mail.me.com",
        "port": 993,
        "security": "ssl",
        "timeout_seconds": 10,
    }


def test_reply_monitor_counts_only_matching_reply_headers_and_retains_no_message_content():
    monitoring = _load_monitoring()
    matching = (
        b"Message-ID: <reply-1@example.invalid>\r\n"
        b"From: dev-recipient@example.invalid\r\n"
        b"In-Reply-To: <outbound-1@example.invalid>\r\n"
        b"Subject: private reply subject\r\n\r\n"
    )
    unrelated = (
        b"Message-ID: <reply-2@example.invalid>\r\n"
        b"From: another@example.invalid\r\n"
        b"References: <outbound-1@example.invalid>\r\n\r\n"
    )
    client = _FakeImap({b"1": matching, b"2": unrelated})

    replies = monitoring._poll_replies_once(
        settings=_settings(),
        username="sender@example.invalid",
        password="app-password",
        development_recipient="dev-recipient@example.invalid",
        outbound_message_id="<outbound-1@example.invalid>",
        imap_factory=lambda *_args, **_kwargs: client,
    )

    assert client.readonly is True
    assert client.logged_out is True
    assert replies == [{"fingerprint": monitoring.hashlib.sha256(b"<reply-1@example.invalid>").hexdigest()}]
    assert "private reply subject" not in repr(replies)
    assert "dev-recipient@example.invalid" not in repr(replies)


def test_reply_monitor_rejects_non_iCloud_imap_endpoint():
    monitoring = _load_monitoring()
    settings = {**_settings(), "host": "imap.example.invalid"}

    try:
        monitoring._poll_replies_once(
            settings=settings,
            username="sender@example.invalid",
            password="app-password",
            development_recipient="dev-recipient@example.invalid",
            outbound_message_id="<outbound-1@example.invalid>",
        )
    except RuntimeError as error:
        assert str(error) == "Reply monitoring must use the approved iCloud IMAP SSL endpoint"
    else:
        raise AssertionError("Expected reply-monitor endpoint validation to fail")


def test_reply_monitor_waits_without_inbox_access_until_an_approved_delivery_exists(tmp_path):
    monitoring = _load_monitoring()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    context = {
        "run_dir": str(run_dir),
        "run_id": "gtm-service-test",
        "config": {"reply_monitoring": {"enabled": True, "poll_interval_seconds": 5}},
    }
    original_interval = monitoring._bounded_float
    monitoring._bounded_float = lambda *_args, **_kwargs: 0.01
    thread = threading.Thread(
        target=monitoring._wait_for_approved_delivery,
        kwargs={
            "context": context,
            "settings": context["config"]["reply_monitoring"],
            "reason": "approved_development_delivery_not_found",
        },
        daemon=True,
    )
    try:
        thread.start()
        state_path = run_dir / monitoring.DEVELOPMENT_REPLY_MONITORING_STATE_PATH
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state.get("status") == "awaiting_approved_development_delivery":
                    break
            time.sleep(0.01)
        else:
            raise AssertionError("Expected the service to wait for an approved delivery")
        (run_dir / "STOP").touch()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert state["reason"] == "approved_development_delivery_not_found"
        assert state["reply_count"] == 0
    finally:
        monitoring._bounded_float = original_interval


def test_disabled_reply_monitor_exits_without_opening_the_inbox_or_keeping_run_alive(tmp_path):
    monitoring = _load_monitoring()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    context = {
        "run_dir": str(run_dir),
        "run_id": "gtm-disabled-monitor-test",
        "config": {"reply_monitoring": {"enabled": False, "poll_interval_seconds": 5}},
    }
    result = monitoring.monitor_development_email_replies(context)

    assert result["status"] == "not_started"
    assert result["reply_monitoring"]["reason"] == "reply_monitoring_disabled"
    assert result["reply_monitoring"]["reply_count"] == 0


def test_human_rejection_keeps_email_unsent_and_ends_the_waiting_service(tmp_path):
    monitoring = _load_monitoring()
    run_id = "gtm-human-rejection-test"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    request_id = monitoring.development_email_approval_request_id(run_id)
    (run_dir / "human.jsonl").write_text(json.dumps({
        "type": "human_input_received",
        "payload": {
            "request_id": request_id,
            "decision": "reject",
            "approved": False,
        },
    }) + "\n", encoding="utf-8")
    context = {
        "run_dir": str(run_dir),
        "run_id": run_id,
        "config": {
            "smtp_delivery": {"enabled": True},
            "reply_monitoring": {"enabled": False, "poll_interval_seconds": 5},
        },
    }
    original_interval = monitoring._bounded_float
    monitoring._bounded_float = lambda *_args, **_kwargs: 0.01
    thread = threading.Thread(
        target=monitoring._wait_for_approved_delivery,
        kwargs={
            "context": context,
            "settings": context["config"]["reply_monitoring"],
            "reason": "approved_development_delivery_not_found",
        },
        daemon=True,
    )
    try:
        thread.start()
        state_path = run_dir / monitoring.DEVELOPMENT_REPLY_MONITORING_STATE_PATH
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state.get("reason") == "human_rejected_or_revised":
                    break
            time.sleep(0.01)
        else:
            raise AssertionError("Expected the rejected request to end the waiting service")
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert not (run_dir / monitoring.DELIVERY_RECEIPT_PATH).exists()
    finally:
        monitoring._bounded_float = original_interval


def test_human_approval_is_converted_to_one_bounded_delivery_authorization(tmp_path):
    monitoring = _load_monitoring()
    run_id = "gtm-human-approval-test"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "draft_customer_interventions.json").write_text(json.dumps({
        "interventions": [{"draft_review": {"approved": True}, "draft": {"subject": "Test"}}],
    }), encoding="utf-8")
    captured = {}
    original_delivery = monitoring.deliver_approved_development_email

    def fake_delivery(context, interventions):
        captured["context"] = context
        captured["interventions"] = interventions
        return {"status": "sent", "message_id": "<approved@test>"}

    monitoring.deliver_approved_development_email = fake_delivery
    try:
        result = monitoring._deliver_after_human_approval({
            "run_dir": str(run_dir),
            "run_id": run_id,
            "config": {},
            "payload": {"business_goal": "Test the reviewed draft."},
        })
    finally:
        monitoring.deliver_approved_development_email = original_delivery

    assert result["status"] == "sent"
    assert captured["context"]["payload"]["business_goal"] == "Test the reviewed draft."
    assert captured["context"]["payload"]["email_send_approval"] == {
        "approved": True,
        "approval_id": f"gtm-development-email:{run_id}",
    }
    assert len(captured["interventions"]) == 1
