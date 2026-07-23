from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_DIR = ROOT / "generic_customer_service_voice_coworker"


def _json_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_customer_service_pre_launch_writes_valid_json_for_quoted_multiline_values(tmp_path):
    run_dir = tmp_path / "run"
    ready_file = run_dir / "pre_launch.ready"
    state_file = run_dir / "post_launch_state.json"
    payload = {
        "inputs": {
            "payload": {
                "business_name": 'Otter "Slice"\nPizza',
                "service_scope": 'Take orders, then say "handoff" when unsure.\nNo payment cards.',
                "opening_message": 'Hi from "Otter Slice".\nWhat can I make?',
                "escalation_policy": 'Escalate "allergy" and refund requests.\nAlways ask a human.',
                "voice": 'aria-"north"',
                "voice_https_port": 7963,
                "voice_local_proxy_port": 8963,
                "knowledge_text": 'Menu says "margherita".\nLine two has basil.',
            }
        }
    }
    env = {
        **os.environ,
        "MN_RUN_ID": "voice-json-unit",
        "MN_RUN_DIR": str(run_dir),
        "MN_PRE_LAUNCH_READY_FILE": str(ready_file),
        "MN_POST_LAUNCH_STATE_FILE": str(state_file),
        "MN_BLUEPRINT_BUNDLE_DIR": str(BLUEPRINT_DIR),
        "MN_BLUEPRINT_CONFIG_JSON": json.dumps(payload),
        "PYTHON_BIN": sys.executable,
    }

    subprocess.run(["bash", str(BLUEPRINT_DIR / "scripts" / "pre-launch.sh")], cwd=BLUEPRINT_DIR, env=env, check=True)

    ready = json.loads(ready_file.read_text(encoding="utf-8"))
    state = json.loads(state_file.read_text(encoding="utf-8"))
    web_ui = json.loads((run_dir / "web_ui.json").read_text(encoding="utf-8"))
    service = json.loads((run_dir / "voice_service.json").read_text(encoding="utf-8"))
    artifact = json.loads((run_dir / "final_artifact.json").read_text(encoding="utf-8"))

    assert ready["env"]["CUSTOMER_SERVICE_BUSINESS_NAME"] == payload["inputs"]["payload"]["business_name"]
    assert ready["config_overrides"]["inputs"]["payload"]["opening_message"] == payload["inputs"]["payload"]["opening_message"]
    assert state["voice_url"] == "https://localhost:8963/customer-service"
    assert web_ui["health_url"] == "https://localhost:8963/health"
    assert service["knowledge_path"].endswith("knowledge/customer_service_knowledge.txt")
    assert artifact["type"] == "customer_service_voice_service"
    assert (run_dir / "knowledge" / "customer_service_knowledge.txt").read_text(encoding="utf-8").startswith(
        'Menu says "margherita".\nLine two has basil.'
    )
    assert _json_lines(run_dir / "events.jsonl")[0]["payload"]["voice_url"] == "https://localhost:8963/customer-service"


def test_customer_service_post_launch_writes_valid_json_for_quoted_state_values(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state_file = run_dir / "post_launch_state.json"
    state_file.write_text(
        json.dumps(
            {
                "voice_url": 'https://localhost:8963/customer-service?shop="otter"',
                "health_url": 'https://localhost:8963/health?probe="yes"',
            }
        ),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "MN_RUN_ID": "voice-post-json-unit",
        "MN_RUN_DIR": str(run_dir),
        "MN_POST_LAUNCH_STATE_FILE": str(state_file),
        "MN_POST_LAUNCH_REASON": 'operator said "done"\ncleanup',
        "PYTHON_BIN": sys.executable,
    }

    subprocess.run(["bash", str(BLUEPRINT_DIR / "scripts" / "post-launch.sh")], cwd=BLUEPRINT_DIR, env=env, check=True)

    artifact = json.loads((run_dir / "final_artifact.json").read_text(encoding="utf-8"))
    events = _json_lines(run_dir / "events.jsonl")
    assert artifact["type"] == "customer_service_voice_service"
    assert events[-1]["type"] == "customer_service_voice_cleanup_completed"
    assert events[-1]["payload"]["reason"] == 'operator said "done"\ncleanup'
    assert events[-1]["payload"]["voice_url"] == 'https://localhost:8963/customer-service?shop="otter"'
