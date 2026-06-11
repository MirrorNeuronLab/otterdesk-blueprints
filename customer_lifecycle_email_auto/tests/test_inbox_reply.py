import importlib.util
import json
from pathlib import Path


BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
EXECUTE_PATH = BLUEPRINT_DIR / "payloads" / "inbox_reply" / "scripts" / "execute.py"


def load_execute_module():
    spec = importlib.util.spec_from_file_location("inbox_reply_execute", EXECUTE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_inbox_reply_renders_personal_reply_template():
    module = load_execute_module()

    html = module.render_reply_html(
        subject="Question about stories",
        reply_text="Thanks for reaching out. Bibblio can help with that.",
        inbound_body="Can you help?",
    )

    assert "Thanks for reaching out" in html
    assert "Manage preferences" not in html
    assert "Unsubscribe" not in html
    assert "data-slot=\"body_section\"" in html


def test_inbox_reply_slack_report_uses_delivery_status(monkeypatch):
    module = load_execute_module()
    sent_messages = []

    def fake_post_slack_message(text):
        sent_messages.append(text)
        return {"status": "sent", "channel": "#test"}

    monkeypatch.setattr(module, "post_slack_message", fake_post_slack_message)

    result = module.send_slack_reply_report(
        to_email="parent@example.com",
        subject="Question about stories",
        delivery={"status": "sent"},
    )

    assert result["status"] == "sent"
    assert "reply to <parent@example.com> was sent" in sent_messages[0]


def test_inbox_reply_saves_sent_email_copy(tmp_path, monkeypatch):
    module = load_execute_module()
    monkeypatch.setenv("SYNAPTIC_SENT_EMAIL_COPY_DIR", str(tmp_path / "copies"))

    result = module.save_sent_email_copy(
        runtime_job_id="job_1",
        to_email="parent@example.com",
        subject="Question about stories",
        text_body="Thanks for reaching out.",
        html_body='<html><body><p data-slot="body_section">Thanks for reaching out.</p></body></html>',
        delivery={"status": "sent", "provider": "agentmail"},
        source="test",
    )

    assert result["status"] == "saved"
    assert Path(result["html_path"]).exists()
    assert Path(result["text_path"]).exists()
    metadata = json.loads(Path(result["metadata_path"]).read_text())
    assert metadata["runtime_job_id"] == "job_1"
    assert metadata["recipient"] == "parent@example.com"
    assert metadata["has_personal_reply_marker"] is True
