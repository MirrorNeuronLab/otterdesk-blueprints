import os
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
PAYLOADS_DIR = BLUEPRINT_DIR / "payloads"


def load_customer_research_execute_module():
    execute_path = PAYLOADS_DIR / "customer_research" / "scripts" / "execute.py"
    spec = importlib.util.spec_from_file_location("customer_research_execute", execute_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_payload_sitecustomize_exposes_shared_marketing_skill():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PAYLOADS_DIR / "customer_research")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from _synaptic_skills.marketing_email import build_customer_brief; print(callable(build_customer_brief))",
        ],
        cwd=BLUEPRINT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_runtime_get_plan_prefers_nested_sandbox_stdout_over_original_input():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PAYLOADS_DIR / "customer_research")
    envelope = {
        "input": {"customer": {"customer_id": "original"}},
        "body": {
            "sandbox": {
                "stdout": json.dumps(
                    {
                        "customer": {"customer_id": "rendered"},
                        "saved_draft": {"draft_id": "draft_rendered"},
                    }
                )
            }
        },
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
                (
                    "import json; "
                    "from _synaptic_runtime.core import get_plan; "
                    f"payload = json.loads({json.dumps(json.dumps(envelope))}); "
                    "print(json.dumps(get_plan(payload), sort_keys=True))"
                ),
        ],
        cwd=BLUEPRINT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["customer"]["customer_id"] == "rendered"
    assert plan["saved_draft"]["draft_id"] == "draft_rendered"


def test_runtime_get_plan_accepts_explicit_emit_body():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PAYLOADS_DIR / "marketing_automation")
    envelope = {
        "body": {
            "customer": {"customer_id": "rendered"},
            "saved_draft": {"draft_id": "draft_rendered"},
        }
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from _synaptic_runtime.core import get_plan; "
                f"payload = json.loads({json.dumps(json.dumps(envelope))}); "
                "print(json.dumps(get_plan(payload), sort_keys=True))"
            ),
        ],
        cwd=BLUEPRINT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["customer"]["customer_id"] == "rendered"
    assert plan["saved_draft"]["draft_id"] == "draft_rendered"


def test_host_local_uploads_shared_skills_with_each_executor():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    workflow_workers = manifest["runtime"]["bindings"]["run_workflow"]["workers"]
    executor_workers = [
        worker
        for worker in workflow_workers
        if (worker.get("with") or {}).get("runner_module") == "MirrorNeuron.Runner.HostLocal"
    ]

    assert executor_workers
    for worker in executor_workers:
        node_config = worker.get("with") or {}
        upload_paths = node_config.get("upload_paths", [])
        sources = {entry["source"] for entry in upload_paths}
        assert "_shared_skills/business_email_campaign_skill" in sources
        assert "_shared_skills/mn_email_delivery_skill" in sources
        assert "_shared_skills/mn_litellm_communicate_skill" in sources
        assert "_shared_skills/mn_external_rate_limit_skill" in sources


def test_manifest_sets_slack_channel_but_not_credentials():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text())
    workflow_workers = manifest["runtime"]["bindings"]["run_workflow"]["workers"]
    secret_slack_keys = {
        "SLACK_BOT_TOKEN",
        "SLACK_API_BASE_URL",
        "MN_SLACK_BOT_TOKEN",
        "MN_SLACK_DEFAULT_CHANNEL",
        "MN_SLACK_API_BASE_URL",
    }

    for worker in workflow_workers:
        env = (worker.get("with") or {}).get("environment", {})
        if env:
            assert not secret_slack_keys & set(env)
            assert env.get("SLACK_DEFAULT_CHANNEL") == "#claw"


def test_campaign_template_selection_keeps_newsletters_on_card_design():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PAYLOADS_DIR / "email_designer")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from _synaptic_runtime.core import load_template_library
from _synaptic_skills.marketing_email import select_template_name

lib = load_template_library()
for campaign in ["program_reminder", "interest_followup", "product_spotlight", "newsletter"]:
    name = select_template_name(plan={"campaign_type": campaign}, template_library=lib)
    assert lib[name]["design_template"] == "card_email.html", (campaign, name)
newsletter = select_template_name(
    plan={
        "campaign_type": "newsletter",
        "customer_brief": {"recommended_template": "personal_reply"},
    },
    template_library=lib,
)
assert lib[newsletter]["design_template"] == "card_email.html"
stale_reply = select_template_name(plan={"campaign_type": "reply_followup"}, template_library=lib)
assert lib[stale_reply]["design_template"] == "card_email.html"
reply = select_template_name(
    plan={
        "campaign_type": "reply_followup",
        "reply_context": {"in_reply_to_message_id": "msg_123"},
    },
    template_library=lib,
)
assert lib[reply]["design_template"] == "personal_reply.html"
print("ok")
""",
        ],
        cwd=BLUEPRINT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_customer_reply_activity_alone_does_not_select_reply_followup():
    module = load_customer_research_execute_module()
    activities = [{"summary": "Customer replied: This sounds interesting."}]

    assert (
        module.should_select_reply_followup(
            plan={"reply_context": {"subject": "Re: Bibblio", "text_body": "Interested"}},
            activities=activities,
            past_campaigns=[],
        )
        is False
    )

    assert (
        module.should_select_reply_followup(
            plan={
                "reply_context": {
                    "subject": "Re: Bibblio",
                    "text_body": "Interested",
                    "in_reply_to_message_id": "msg_123",
                }
            },
            activities=activities,
            past_campaigns=[],
        )
        is True
    )


def test_slack_defaults_to_claw_channel_without_channel_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PAYLOADS_DIR / "_shared_skills")
    env["SLACK_BOT_TOKEN"] = "test-token"
    env.pop("SLACK_DEFAULT_CHANNEL", None)
    env.pop("MN_SLACK_DEFAULT_CHANNEL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import urllib.error
import mn_email_delivery_skill.email_delivery as email_delivery

def fake_urlopen(request, timeout):
    raise urllib.error.URLError("stop")

email_delivery.urllib.request.urlopen = fake_urlopen
result = email_delivery.post_slack_message("hello", channel=None)
print(result["channel"])
""",
        ],
        cwd=BLUEPRINT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "#claw"


def test_customer_research_runs_with_blueprint_local_campaign_skill(tmp_path):
    planned_actions = json.loads((BLUEPRINT_DIR / "planned_actions.json").read_text())
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"input": planned_actions[0]["payload"]}))
    db_path = tmp_path / "runtime.db"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PAYLOADS_DIR / "customer_research")
    env["MN_INPUT_FILE"] = str(input_file)
    env["SYNAPTIC_DB_PATH"] = str(db_path)
    for key in (
        "SECONDARY_LITELLM_API_KEY",
        "SECONDARY_LLM_API_KEY",
        "PRIMARY_LITELLM_API_KEY",
        "PRIMARY_LLM_API_KEY",
        "LITELLM_API_KEY",
        "LLM_API_KEY",
        "GEMINI_API_KEY",
    ):
        env.pop(key, None)

    result = subprocess.run(
        [
            sys.executable,
            str(PAYLOADS_DIR / "customer_research" / "scripts" / "execute.py"),
        ],
        cwd=BLUEPRINT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    if payload.get("existing_draft"):
        assert payload["existing_draft"]["status"] == "ready"
        assert payload["existing_draft"]["subject"]
    else:
        assert payload["customer_brief"]["recommended_template"]
        assert payload["audience_segment"]


def test_fresh_runtime_db_is_seeded_from_input_data(tmp_path):
    db_path = tmp_path / "fresh_runtime.db"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PAYLOADS_DIR / "customer_research")
    env["SYNAPTIC_DB_PATH"] = str(db_path)
    env.pop("SYNAPTIC_DB_CONNECTION", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from _synaptic_runtime.core import db_connect; "
                "conn = db_connect(); "
                "first = {"
                "'activities': conn.execute('SELECT COUNT(*) FROM customer_marketing_activity').fetchone()[0], "
                "'drafts': conn.execute('SELECT COUNT(*) FROM email_drafts').fetchone()[0], "
                "'sent_drafts': conn.execute(\"SELECT COUNT(*) FROM email_drafts WHERE status = 'sent'\").fetchone()[0], "
                "'ready_drafts': conn.execute(\"SELECT COUNT(*) FROM email_drafts WHERE status = 'ready'\").fetchone()[0], "
                "'ready_html': conn.execute(\"SELECT html_body FROM email_drafts WHERE status = 'ready' ORDER BY draft_id LIMIT 1\").fetchone()[0]"
                "}; "
                "conn.close(); "
                "conn = db_connect(); "
                "second = {"
                "'activities': conn.execute('SELECT COUNT(*) FROM customer_marketing_activity').fetchone()[0], "
                "'drafts': conn.execute('SELECT COUNT(*) FROM email_drafts').fetchone()[0], "
                "'sent_drafts': conn.execute(\"SELECT COUNT(*) FROM email_drafts WHERE status = 'sent'\").fetchone()[0], "
                "'ready_drafts': conn.execute(\"SELECT COUNT(*) FROM email_drafts WHERE status = 'ready'\").fetchone()[0], "
                "'ready_html': conn.execute(\"SELECT html_body FROM email_drafts WHERE status = 'ready' ORDER BY draft_id LIMIT 1\").fetchone()[0]"
                "}; "
                "conn.close(); "
                "print(json.dumps({'first': first, 'second': second}, sort_keys=True))"
            ),
        ],
        cwd=BLUEPRINT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    counts = payload["first"]
    assert counts["activities"] >= 6
    assert counts["drafts"] >= 3
    assert counts["sent_drafts"] >= 1
    assert counts["ready_drafts"] >= 2
    assert "Story moments to explore" in counts["ready_html"]
    assert "data-slot=\"headline\"" in counts["ready_html"]
    assert payload["second"] == counts


def test_payload_seed_copies_match_root_input_data():
    root_seed = (BLUEPRINT_DIR / "input" / "data" / "bootstrap_seed.json").read_text()
    payload_inputs = sorted(PAYLOADS_DIR.glob("*/input"))

    assert payload_inputs
    for input_dir in payload_inputs:
        assert (input_dir / "data" / "bootstrap_seed.json").read_text() == root_seed
