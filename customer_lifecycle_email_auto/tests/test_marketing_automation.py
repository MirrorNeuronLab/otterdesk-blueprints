import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
EXECUTE_PATH = BLUEPRINT_DIR / "payloads" / "marketing_automation" / "scripts" / "execute.py"


def load_execute_module():
    spec = importlib.util.spec_from_file_location("marketing_automation_execute", EXECUTE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def init_runtime_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE email_drafts (
                draft_id TEXT PRIMARY KEY,
                customer_id TEXT,
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
        conn.execute(
            """
            CREATE TABLE customer_marketing_activity (
                activity_id TEXT PRIMARY KEY,
                customer_id TEXT,
                summary TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE agent_logs (
                runtime_job_id TEXT,
                agent_id TEXT,
                level TEXT,
                message TEXT,
                details_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO email_drafts (
                draft_id,
                customer_id,
                status,
                subject,
                preview_text,
                body_text,
                html_body,
                scheduled_send_at,
                prepared_at,
                provider_id,
                sent_at,
                from_email,
                thread_message_id,
                in_reply_to_message_id,
                references_message_ids_json,
                source_payload_json
            ) VALUES (?, ?, 'ready', ?, ?, ?, ?, ?, ?, '', '', ?, '', '', '[]', '{}')
            """,
            (
                "draft_test",
                "cust_1",
                "A small story idea",
                "A tiny preview",
                "Plain text body",
                "<p>Plain text body</p>",
                "2026-04-15T00:20:00+00:00",
                "2026-04-15T00:19:30+00:00",
                "hello@example.com",
            ),
        )


class MarketingAutomationTests(unittest.TestCase):
    def setUp(self):
        self.previous_env = os.environ.copy()
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "runtime.db")
        self.input_path = os.path.join(self.tmp.name, "input.json")
        self.sent_email_copy_dir = os.path.join(self.tmp.name, "sent_email_copies")
        init_runtime_db(self.db_path)
        os.environ["SYNAPTIC_DB_PATH"] = self.db_path
        os.environ["SYNAPTIC_DB_CONNECTION"] = f"sqlite:///{self.db_path}"
        os.environ["MN_INPUT_FILE"] = self.input_path
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = ""
        os.environ["SYNAPTIC_EMAIL_DELIVERY_MODE"] = "agentmail"
        os.environ["SYNAPTIC_EMIT_CYCLE_TRIGGER"] = "false"
        os.environ["SYNAPTIC_SENT_EMAIL_COPY_DIR"] = self.sent_email_copy_dir

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.previous_env)
        self.tmp.cleanup()

    def write_plan(self):
        plan = {
            "runtime_job_id": "job_1",
            "cycle": 2,
            "campaign_type": "parent_awareness",
            "customer": {
                "customer_id": "cust_1",
                "name": "Avery",
                "email": "avery@example.com",
            },
            "control_decision": {"decision": "send_now"},
            "policy_decision": {"decision": "allow"},
            "saved_draft": {
                "draft_id": "draft_test",
                "subject": "A small story idea",
                "body_text": "Plain text body",
                "html_body": "<p>Plain text body</p>",
            },
        }
        Path(self.input_path).write_text(json.dumps(plan))

    def test_injected_email_sender_logs_sent_event(self):
        self.write_plan()
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()
        sent_requests = []
        slack_messages = []

        def fake_email_sender(request):
            sent_requests.append(request)
            return {"status": "sent", "provider_id": "fake_provider", "http_status": 200}

        def fake_slack_sender(text):
            slack_messages.append(text)
            return {"status": "sent", "channel": "#test"}

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(email_sender=fake_email_sender, slack_sender=fake_slack_sender)

        payload = json.loads(output.getvalue())
        self.assertEqual(sent_requests[0]["to"], ["test@example.com"])
        self.assertIn('data-slot="headline"', sent_requests[0]["html"])
        self.assertIn("Plain text body", sent_requests[0]["html"])
        self.assertEqual(payload["events"][0]["payload"]["status"], "sent")
        self.assertEqual(payload["events"][0]["payload"]["subject"], "A small story idea")
        sent_copy = payload["events"][0]["payload"]["sent_email_copy"]
        self.assertEqual(sent_copy["status"], "saved")
        self.assertTrue(Path(sent_copy["html_path"]).exists())
        self.assertTrue(Path(sent_copy["text_path"]).exists())
        self.assertTrue(Path(sent_copy["metadata_path"]).exists())
        self.assertIn("Plain text body", Path(sent_copy["html_path"]).read_text())
        metadata = json.loads(Path(sent_copy["metadata_path"]).read_text())
        self.assertEqual(metadata["runtime_job_id"], "job_1")
        self.assertEqual(metadata["recipient"], "test@example.com")
        self.assertTrue(metadata["has_card_email_marker"])
        self.assertIn("round 2 report: 1 succeeded, 0 failed", slack_messages[0])
        self.assertIn(
            {
                "type": "slack_round_report_attempted",
                "payload": {
                    "customer_id": "cust_1",
                    "email": "test@example.com",
                    "customer_email": "avery@example.com",
                    "cycle": 2,
                    "success_count": 1,
                    "failed_count": 0,
                    "attempted_count": 1,
                    "status": "sent",
                    "channel": "#test",
                    "reason": None,
                },
            },
            payload["events"],
        )
        self.assertIn(
            {
                "type": "email_sent",
                "payload": {"to": "test@example.com", "subject": "A small story idea"},
            },
            payload["events"],
        )

        with sqlite3.connect(self.db_path) as conn:
            log = conn.execute(
                "SELECT details_json FROM agent_logs WHERE message = 'Email sent event.'"
            ).fetchone()
        self.assertIsNotNone(log)
        self.assertEqual(
            json.loads(log[0]),
            {"to": "test@example.com", "subject": "A small story idea"},
        )

    def test_delivery_rerenders_old_default_html_with_card_template(self):
        self.write_plan()
        plan = json.loads(Path(self.input_path).read_text())
        plan["saved_draft"]["html_body"] = (
            "<html><body style='background-color:#f5f1e8;'>"
            "<h1 data-slot='headline'>Old fallback</h1>"
            "<p data-slot='body_section'>Plain text body</p>"
            "<a data-slot='cta_button' href='https://example.com?utm_campaign=old'>Open</a>"
            "</body></html>"
        )
        Path(self.input_path).write_text(json.dumps(plan))
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()
        sent_requests = []

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda request: sent_requests.append(request)
                or {"status": "sent", "provider_id": "fake_provider", "http_status": 200},
                slack_sender=lambda _text: {"status": "sent", "channel": "#test"},
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["events"][0]["payload"]["status"], "sent")
        self.assertIn("Story moments to explore", sent_requests[0]["html"])
        self.assertIn("background-image:linear-gradient(135deg,#dff5fb", sent_requests[0]["html"])
        self.assertNotIn("background-color:#f5f1e8", sent_requests[0]["html"])

    def test_delivery_rerenders_stale_reply_followup_as_card_without_thread_context(self):
        self.write_plan()
        plan = json.loads(Path(self.input_path).read_text())
        plan.pop("campaign_type", None)
        plan["saved_draft"]["html_body"] = (
            '<html><body><p data-slot="body_section">Old personal reply</p></body></html>'
        )
        plan["saved_draft"]["source_payload_json"] = json.dumps(
            {
                "campaign_type": "reply_followup",
                "customer": plan["customer"],
                "customer_brief": {"recommended_template": "personal_reply"},
                "draft": {
                    "subject": "Re: A small story idea",
                    "body_sections": ["Plain text body"],
                },
                "design": {
                    "template": "personal_reply",
                    "html_body": '<html><body><p data-slot="body_section">Old personal reply</p></body></html>',
                },
            }
        )
        Path(self.input_path).write_text(json.dumps(plan))
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()
        sent_requests = []

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda request: sent_requests.append(request)
                or {"status": "sent", "provider_id": "fake_provider", "http_status": 200},
                slack_sender=lambda _text: {"status": "sent", "channel": "#test"},
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["events"][0]["payload"]["status"], "sent")
        self.assertIn("Story moments to explore", sent_requests[0]["html"])
        self.assertIn("background-image:linear-gradient(135deg,#dff5fb", sent_requests[0]["html"])
        self.assertNotIn("Old personal reply", sent_requests[0]["html"])

    def test_quick_testing_mode_dry_runs_without_email_sender(self):
        self.write_plan()
        os.environ["SYNAPTIC_EMAIL_DELIVERY_MODE"] = "dry_run"
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()
        slack_messages = []

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                slack_sender=lambda text: slack_messages.append(text)
                or {"status": "sent", "channel": "#test"},
            )

        payload = json.loads(output.getvalue())
        event = payload["events"][0]["payload"]
        self.assertEqual(event["status"], "sent")
        self.assertEqual(event["provider_id"], "dry_run")
        self.assertTrue(event["dry_run"])
        self.assertTrue(event["quick_testing"])
        self.assertIn("round 2 report: 1 succeeded, 0 failed", slack_messages[0])
        self.assertIn(
            {
                "type": "email_sent",
                "payload": {"to": "test@example.com", "subject": "A small story idea"},
            },
            payload["events"],
        )
        slack_event = next(
            event
            for event in payload["events"]
            if event["type"] == "slack_round_report_attempted"
        )
        self.assertEqual(slack_event["payload"]["status"], "sent")

    def test_unwraps_nested_original_plan_before_sending(self):
        self.write_plan()
        original_plan = json.loads(Path(self.input_path).read_text())
        Path(self.input_path).write_text(
            json.dumps({"original_plan": original_plan, "cycle": 4})
        )
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda _request: {
                    "status": "sent",
                    "provider_id": "fake_provider",
                    "http_status": 200,
                },
                slack_sender=lambda _text: {"status": "sent", "channel": "#test"},
            )

        payload = json.loads(output.getvalue())
        event = payload["events"][0]["payload"]
        self.assertEqual(event["status"], "sent")
        self.assertEqual(event["cycle"], 4)

    def test_prefers_sandbox_stdout_plan_with_saved_draft_over_original_input(self):
        self.write_plan()
        original_plan = json.loads(Path(self.input_path).read_text())
        sent_plan = dict(original_plan)
        sent_plan["cycle"] = 5
        envelope = {
            "input": {
                "customer": original_plan["customer"],
                "cycle": 5,
            },
            "sandbox": {
                "stdout": json.dumps(sent_plan),
            },
        }
        Path(self.input_path).write_text(json.dumps(envelope))
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda _request: {
                    "status": "sent",
                    "provider_id": "fake_provider",
                    "http_status": 200,
                },
                slack_sender=lambda _text: {"status": "sent", "channel": "#test"},
            )

        payload = json.loads(output.getvalue())
        event = payload["events"][0]["payload"]
        self.assertEqual(event["status"], "sent")
        self.assertEqual(event["cycle"], 5)

    def test_skips_non_delivery_control_messages_without_crashing(self):
        Path(self.input_path).write_text(json.dumps({"events": [], "cycle": 2}))
        module = load_execute_module()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main()

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["events"][0]["type"], "email_delivery_skipped")
        self.assertEqual(payload["events"][0]["payload"]["reason"], "missing_customer_plan")
        self.assertEqual(payload["emit_messages"], [])

    def test_loads_pending_ready_draft_when_runtime_message_lacks_saved_draft(self):
        plan = {
            "runtime_job_id": "job_1",
            "cycle": 2,
            "customer": {
                "customer_id": "cust_1",
                "name": "Avery",
                "email": "avery@example.com",
            },
            "control_decision": {"decision": "send_now"},
            "policy_decision": {"decision": "allow"},
        }
        Path(self.input_path).write_text(json.dumps(plan))
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda _request: {
                    "status": "sent",
                    "provider_id": "fake_provider",
                    "http_status": 200,
                },
                slack_sender=lambda _text: {"status": "sent", "channel": "#test"},
            )

        payload = json.loads(output.getvalue())
        event = payload["events"][0]["payload"]
        self.assertEqual(event["status"], "sent")
        self.assertEqual(event["subject"], "A small story idea")

    def test_test_mode_sends_only_one_email_per_campaign_action(self):
        self.write_plan()
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()
        sent_requests = []

        def fake_email_sender(request):
            sent_requests.append(request)
            return {"status": "sent", "provider_id": "fake_provider", "http_status": 200}

        first_output = io.StringIO()
        with contextlib.redirect_stdout(first_output):
            module.main(email_sender=fake_email_sender, slack_sender=lambda _text: {})

        second_output = io.StringIO()
        with contextlib.redirect_stdout(second_output):
            module.main(email_sender=fake_email_sender, slack_sender=lambda _text: {})

        first_payload = json.loads(first_output.getvalue())
        second_payload = json.loads(second_output.getvalue())
        self.assertEqual(len(sent_requests), 1)
        self.assertEqual(first_payload["events"][0]["payload"]["status"], "sent")
        self.assertEqual(second_payload["events"][0]["type"], "email_delivery_skipped")
        self.assertEqual(
            second_payload["events"][0]["payload"]["reason"],
            "duplicate_test_action",
        )
        self.assertEqual(second_payload["emit_messages"], [])

    def test_test_mode_duplicate_guard_is_scoped_to_runtime_job(self):
        self.write_plan()
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        module = load_execute_module()
        sent_requests = []

        def fake_email_sender(request):
            sent_requests.append(request)
            return {"status": "sent", "provider_id": "fake_provider", "http_status": 200}

        first_output = io.StringIO()
        with contextlib.redirect_stdout(first_output):
            module.main(email_sender=fake_email_sender, slack_sender=lambda _text: {})

        next_job_plan = json.loads(Path(self.input_path).read_text())
        next_job_plan["runtime_job_id"] = "job_2"
        Path(self.input_path).write_text(json.dumps(next_job_plan))

        second_output = io.StringIO()
        with contextlib.redirect_stdout(second_output):
            module.main(email_sender=fake_email_sender, slack_sender=lambda _text: {})

        first_payload = json.loads(first_output.getvalue())
        second_payload = json.loads(second_output.getvalue())
        self.assertEqual(len(sent_requests), 2)
        self.assertEqual(first_payload["events"][0]["payload"]["status"], "sent")
        self.assertEqual(second_payload["events"][0]["payload"]["status"], "sent")

    def test_test_mode_sent_non_final_action_emits_next_cycle(self):
        self.write_plan()
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        os.environ["SYNAPTIC_EMIT_CYCLE_TRIGGER"] = "true"
        module = load_execute_module()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda _request: {
                    "status": "sent",
                    "provider_id": "fake_provider",
                    "http_status": 200,
                },
                slack_sender=lambda _text: {},
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["events"][0]["payload"]["status"], "sent")
        self.assertEqual(payload["emit_messages"][0]["to"], "monitor_scheduler_agent")
        self.assertEqual(payload["emit_messages"][0]["type"], "cycle_trigger")
        self.assertEqual(payload["emit_messages"][0]["body"]["cycle"], 3)

    def test_failed_delivery_does_not_emit_next_cycle(self):
        self.write_plan()
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        os.environ["SYNAPTIC_EMIT_CYCLE_TRIGGER"] = "true"
        module = load_execute_module()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda _request: {
                    "status": "failed",
                    "error": "provider throttled",
                },
                slack_sender=lambda _text: {},
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["events"][0]["payload"]["status"], "failed")
        self.assertEqual(payload["emit_messages"], [])

    def test_test_mode_default_cycle_cap_stops_next_cycle(self):
        self.write_plan()
        plan = json.loads(Path(self.input_path).read_text())
        plan["cycle"] = 3
        Path(self.input_path).write_text(json.dumps(plan))
        os.environ["SYNAPTIC_TEST_EMAIL_TO"] = "test@example.com"
        os.environ["SYNAPTIC_EMIT_CYCLE_TRIGGER"] = "true"
        module = load_execute_module()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda _request: {
                    "status": "sent",
                    "provider_id": "fake_provider",
                    "http_status": 200,
                },
                slack_sender=lambda _text: {},
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["events"][0]["payload"]["status"], "sent")
        self.assertEqual(payload["emit_messages"], [])

    def test_round_slack_report_accumulates_success_and_failure_counts(self):
        self.write_plan()
        module = load_execute_module()
        slack_messages = []

        first_output = io.StringIO()
        with contextlib.redirect_stdout(first_output):
            module.main(
                email_sender=lambda _request: {
                    "status": "sent",
                    "provider_id": "fake_provider",
                    "http_status": 200,
                },
                slack_sender=lambda text: slack_messages.append(text)
                or {"status": "sent", "channel": "#test"},
            )

        second_plan = json.loads(Path(self.input_path).read_text())
        second_plan["customer"] = {
            "customer_id": "cust_2",
            "name": "Blake",
            "email": "blake@example.com",
        }
        second_plan["saved_draft"] = {
            **second_plan["saved_draft"],
            "draft_id": "draft_failed",
        }
        Path(self.input_path).write_text(json.dumps(second_plan))

        second_output = io.StringIO()
        with contextlib.redirect_stdout(second_output):
            module.main(
                email_sender=lambda _request: {"status": "failed", "error": "boom"},
                slack_sender=lambda text: slack_messages.append(text)
                or {"status": "sent", "channel": "#test"},
            )

        first_payload = json.loads(first_output.getvalue())
        second_payload = json.loads(second_output.getvalue())
        self.assertIn("round 2 report: 1 succeeded, 0 failed", slack_messages[0])
        self.assertIn("round 2 report: 1 succeeded, 1 failed", slack_messages[1])
        self.assertEqual(
            first_payload["next_state"]["last_round_delivery_report"]["success_count"],
            1,
        )
        self.assertEqual(
            second_payload["next_state"]["last_round_delivery_report"]["failed_count"],
            1,
        )

    def test_slack_report_error_does_not_fail_email_delivery(self):
        self.write_plan()
        module = load_execute_module()

        def broken_slack_sender(_text):
            raise RuntimeError("slack api unavailable")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main(
                email_sender=lambda _request: {
                    "status": "sent",
                    "provider_id": "fake_provider",
                    "http_status": 200,
                },
                slack_sender=broken_slack_sender,
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["events"][0]["payload"]["status"], "sent")
        slack_event = next(
            event
            for event in payload["events"]
            if event["type"] == "slack_round_report_attempted"
        )
        self.assertEqual(slack_event["payload"]["status"], "failed")
        self.assertEqual(slack_event["payload"]["reason"], "slack_report_error")


if __name__ == "__main__":
    unittest.main()
