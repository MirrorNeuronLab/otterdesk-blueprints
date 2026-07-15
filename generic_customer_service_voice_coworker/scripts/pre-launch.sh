#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${MN_RUN_ID:-customer-service-voice-dev}"
RUN_DIR="${MN_RUN_DIR:-$HOME/.mn/runs/${RUN_ID}}"
CONFIG_JSON="${MN_BLUEPRINT_CONFIG_JSON:-}"
if [[ -z "${CONFIG_JSON}" ]]; then
  CONFIG_JSON="{}"
fi
READY_FILE="${MN_PRE_LAUNCH_READY_FILE:-${RUN_DIR}/pre_launch.ready}"
STATE_FILE="${MN_POST_LAUNCH_STATE_FILE:-${RUN_DIR}/post_launch_state.json}"
BUNDLE_DIR="${MN_BLUEPRINT_BUNDLE_DIR:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

mkdir -p "${RUN_DIR}/knowledge"

eval "$(
  CONFIG_JSON="${CONFIG_JSON}" "${PYTHON_BIN}" - <<'PY'
import json
import os
import shlex

try:
    config = json.loads(os.environ.get("CONFIG_JSON") or "{}")
except json.JSONDecodeError:
    config = {}
payload = ((config.get("inputs") or {}).get("payload") or {})
values = {
    "BUSINESS_NAME": payload.get("business_name") or "Otter Slice Pizza",
    "SERVICE_SCOPE": payload.get("service_scope") or "Take pizza orders from the editable menu knowledge, collect pickup or delivery details, and recommend human handoff when needed.",
    "OPENING_MESSAGE": payload.get("opening_message") or "Thanks for calling Otter Slice Pizza. What delicious trouble can I help you get into today?",
    "ESCALATION_POLICY": payload.get("escalation_policy") or "Escalate allergies, food-safety concerns, refunds, complaints, payment-card questions, missing orders, angry callers, and anything not grounded in the knowledge base.",
    "VOICE_NAME": payload.get("voice") or "aria",
    "VOICE_PORT": str(payload.get("voice_https_port") or 7863),
    "LOCAL_PROXY_PORT": str(payload.get("voice_local_proxy_port") or payload.get("local_proxy_port") or payload.get("voice_https_port") or 7863),
    "KNOWLEDGE_TEXT": payload.get("knowledge_text") or "",
}
for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)"

VOICE_URL="${CUSTOMER_SERVICE_PUBLIC_URL:-https://localhost:${LOCAL_PROXY_PORT}/customer-service}"
HEALTH_URL="${CUSTOMER_SERVICE_HEALTH_URL:-https://localhost:${LOCAL_PROXY_PORT}/health}"
KNOWLEDGE_PATH="${RUN_DIR}/knowledge/customer_service_knowledge.txt"

if [[ -z "${KNOWLEDGE_TEXT}" ]]; then
  if [[ -f "${BUNDLE_DIR}/payloads/agents/voice_service/knowledge/default_knowledge.txt" ]]; then
    KNOWLEDGE_TEXT="$(cat "${BUNDLE_DIR}/payloads/agents/voice_service/knowledge/default_knowledge.txt")"
  elif [[ -f "${BUNDLE_DIR}/knowledge/default_knowledge.txt" ]]; then
    KNOWLEDGE_TEXT="$(cat "${BUNDLE_DIR}/knowledge/default_knowledge.txt")"
  else
    KNOWLEDGE_TEXT="Generic customer-service knowledge is not configured yet."
  fi
fi
printf "%s\n" "${KNOWLEDGE_TEXT}" > "${KNOWLEDGE_PATH}"

append_event() {
  local event_type="$1"
  local payload="$2"
  "${PYTHON_BIN}" - "${RUN_DIR}/events.jsonl" "${event_type}" "${payload}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
record = {
    "type": sys.argv[2],
    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "payload": json.loads(sys.argv[3]),
    "source": "customer_service_pre_launch",
}
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY
}

VOICE_PREPARED_PAYLOAD="$(
  VOICE_URL="${VOICE_URL}" "${PYTHON_BIN}" - <<'PY'
import json
import os

print(json.dumps({
    "voice_url": os.environ["VOICE_URL"],
    "requires": "nvidia-accelerated-node",
}))
PY
)"
append_event "customer_service_voice_prepared" "${VOICE_PREPARED_PAYLOAD}"

RUN_ID="${RUN_ID}" \
RUN_DIR="${RUN_DIR}" \
STATE_FILE="${STATE_FILE}" \
READY_FILE="${READY_FILE}" \
BUSINESS_NAME="${BUSINESS_NAME}" \
SERVICE_SCOPE="${SERVICE_SCOPE}" \
OPENING_MESSAGE="${OPENING_MESSAGE}" \
ESCALATION_POLICY="${ESCALATION_POLICY}" \
VOICE_NAME="${VOICE_NAME}" \
VOICE_PORT="${VOICE_PORT}" \
LOCAL_PROXY_PORT="${LOCAL_PROXY_PORT}" \
VOICE_URL="${VOICE_URL}" \
HEALTH_URL="${HEALTH_URL}" \
KNOWLEDGE_PATH="${KNOWLEDGE_PATH}" \
"${PYTHON_BIN}" - <<'PY'
import json
import os
from pathlib import Path


def require_int(name: str) -> int:
    return int(str(os.environ[name]).strip())


def write_json(path: str | Path, value: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


run_id = os.environ["RUN_ID"]
run_dir = Path(os.environ["RUN_DIR"])
voice_port = require_int("VOICE_PORT")
local_proxy_port = require_int("LOCAL_PROXY_PORT")
voice_url = os.environ["VOICE_URL"]
health_url = os.environ["HEALTH_URL"]
knowledge_path = os.environ["KNOWLEDGE_PATH"]
business_name = os.environ["BUSINESS_NAME"]
service_scope = os.environ["SERVICE_SCOPE"]
opening_message = os.environ["OPENING_MESSAGE"]
escalation_policy = os.environ["ESCALATION_POLICY"]
voice_name = os.environ["VOICE_NAME"]

write_json(
    os.environ["STATE_FILE"],
    {
        "schema_version": "mn.blueprint.customer_service_voice.pre_launch_state.v1",
        "run_id": run_id,
        "voice_port": voice_port,
        "local_proxy_port": local_proxy_port,
        "voice_url": voice_url,
        "health_url": health_url,
        "knowledge_path": knowledge_path,
        "stack_status": "runtime_required",
    },
)

write_json(
    run_dir / "web_ui.json",
    {
        "schema_version": "mn.blueprint.web_ui.v1",
        "adapter": "gradio",
        "blueprint_id": "generic_customer_service_voice_coworker",
        "run_id": run_id,
        "voice_url": voice_url,
        "health_url": health_url,
        "knowledge_path": "knowledge/customer_service_knowledge.txt",
        "conversation_path": "conversation.jsonl",
        "status": "prepared",
    },
)

write_json(
    run_dir / "voice_service.json",
    {
        "schema_version": "mn.blueprint.voice_service.v1",
        "blueprint_id": "generic_customer_service_voice_coworker",
        "run_id": run_id,
        "public_url": voice_url,
        "health_url": health_url,
        "knowledge_path": knowledge_path,
        "status": "prepared",
    },
)

write_json(
    run_dir / "final_artifact.json",
    {
        "type": "customer_service_voice_service",
        "executive_summary": "The pizza-ordering voice co-worker is prepared for an NVIDIA-accelerated runtime launch.",
        "recommended_action": f"Open {voice_url} after the runtime voice node starts.",
        "confidence": 0.75,
        "evidence": [
            {"source": "pre_launch.ready", "detail": "Run-scoped knowledge was prepared."},
            {"source": "voice_service.json", "detail": "Voice URL and health URL were recorded."},
        ],
        "next_steps": [
            "Confirm the cluster has a DGX Spark, GH200, H100, H200, B200, or GB200 class node.",
            "Start the blueprint runtime.",
            "Open the voice URL and test microphone conversation.",
        ],
        "source_refs": ["web_ui.json", "voice_service.json", "knowledge/customer_service_knowledge.txt", "events.jsonl"],
    },
)

write_json(
    os.environ["READY_FILE"],
    {
        "env": {
            "CUSTOMER_SERVICE_RUN_ID": run_id,
            "CUSTOMER_SERVICE_RUN_DIR": str(run_dir),
            "CUSTOMER_SERVICE_BUSINESS_NAME": business_name,
            "CUSTOMER_SERVICE_SCOPE": service_scope,
            "CUSTOMER_SERVICE_OPENING_MESSAGE": opening_message,
            "CUSTOMER_SERVICE_ESCALATION_POLICY": escalation_policy,
            "CUSTOMER_SERVICE_VOICE": voice_name,
            "MAGPIE_VOICE": voice_name,
            "CUSTOMER_SERVICE_KNOWLEDGE_PATH": knowledge_path,
            "CUSTOMER_SERVICE_PUBLIC_URL": voice_url,
            "CUSTOMER_SERVICE_HEALTH_URL": health_url,
            "VOICE_HTTPS_PORT": str(voice_port),
            "MN_LLM_PROVIDER": "docker_model_runner",
            "CUSTOMER_SERVICE_STACK_WAIT_SECONDS": "900",
        },
        "config_overrides": {
            "inputs": {
                "payload": {
                    "business_name": business_name,
                    "service_scope": service_scope,
                    "opening_message": opening_message,
                    "escalation_policy": escalation_policy,
                    "voice": voice_name,
                    "voice_https_port": voice_port,
                    "voice_local_proxy_port": local_proxy_port,
                    "voice_public_url": voice_url,
                }
            },
            "web_ui": {
                "dashboard": {
                    "voice_url": voice_url,
                    "health_url": health_url,
                    "knowledge_artifact": "knowledge/customer_service_knowledge.txt",
                    "conversation_artifact": "conversation.jsonl",
                }
            },
        },
    },
)
PY
