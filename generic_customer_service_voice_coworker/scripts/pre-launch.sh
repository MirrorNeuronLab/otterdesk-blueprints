#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${MN_RUN_ID:-customer-service-voice-dev}"
RUN_DIR="${MN_RUN_DIR:-$HOME/.mn/runs/${RUN_ID}}"
CONFIG_JSON="${MN_BLUEPRINT_CONFIG_JSON:-{}}"
READY_FILE="${MN_PRE_LAUNCH_READY_FILE:-${RUN_DIR}/pre_launch.ready}"
STATE_FILE="${MN_POST_LAUNCH_STATE_FILE:-${RUN_DIR}/post_launch_state.json}"
BUNDLE_DIR="${MN_BLUEPRINT_BUNDLE_DIR:-$(pwd)}"

mkdir -p "${RUN_DIR}/knowledge"

eval "$(
  CONFIG_JSON="${CONFIG_JSON}" python3 - <<'PY'
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
  if [[ -f "${BUNDLE_DIR}/payloads/voice_service/knowledge/default_knowledge.txt" ]]; then
    KNOWLEDGE_TEXT="$(cat "${BUNDLE_DIR}/payloads/voice_service/knowledge/default_knowledge.txt")"
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
  python3 - "${RUN_DIR}/events.jsonl" "${event_type}" "${payload}" <<'PY'
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

append_event "customer_service_voice_prepared" "{\"voice_url\":\"${VOICE_URL}\",\"requires\":\"nvidia-accelerated-node\"}"

cat > "${STATE_FILE}" <<JSON
{
  "schema_version": "mn.blueprint.customer_service_voice.pre_launch_state.v1",
  "run_id": "${RUN_ID}",
  "voice_port": ${VOICE_PORT},
  "local_proxy_port": ${LOCAL_PROXY_PORT},
  "voice_url": "${VOICE_URL}",
  "health_url": "${HEALTH_URL}",
  "knowledge_path": "${KNOWLEDGE_PATH}",
  "stack_status": "runtime_required"
}
JSON

cat > "${RUN_DIR}/web_ui.json" <<JSON
{
  "schema_version": "mn.blueprint.web_ui.v1",
  "adapter": "gradio",
  "blueprint_id": "generic_customer_service_voice_coworker",
  "run_id": "${RUN_ID}",
  "voice_url": "${VOICE_URL}",
  "health_url": "${HEALTH_URL}",
  "knowledge_path": "knowledge/customer_service_knowledge.txt",
  "conversation_path": "conversation.jsonl",
  "status": "prepared"
}
JSON

cat > "${RUN_DIR}/voice_service.json" <<JSON
{
  "schema_version": "mn.blueprint.voice_service.v1",
  "blueprint_id": "generic_customer_service_voice_coworker",
  "run_id": "${RUN_ID}",
  "public_url": "${VOICE_URL}",
  "health_url": "${HEALTH_URL}",
  "knowledge_path": "${KNOWLEDGE_PATH}",
  "status": "prepared"
}
JSON

cat > "${RUN_DIR}/final_artifact.json" <<JSON
{
  "type": "customer_service_voice_service",
  "executive_summary": "The pizza-ordering voice co-worker is prepared for an NVIDIA-accelerated runtime launch.",
  "recommended_action": "Open ${VOICE_URL} after the runtime voice node starts.",
  "confidence": 0.75,
  "evidence": [
    {"source": "pre_launch.ready", "detail": "Run-scoped knowledge was prepared."},
    {"source": "voice_service.json", "detail": "Voice URL and health URL were recorded."}
  ],
  "next_steps": [
    "Confirm the cluster has a DGX Spark, GH200, H100, H200, B200, or GB200 class node.",
    "Start the blueprint runtime.",
    "Open the voice URL and test microphone conversation."
  ],
  "source_refs": ["web_ui.json", "voice_service.json", "knowledge/customer_service_knowledge.txt", "events.jsonl"]
}
JSON

cat > "${READY_FILE}" <<JSON
{
  "env": {
    "CUSTOMER_SERVICE_RUN_ID": "${RUN_ID}",
    "CUSTOMER_SERVICE_RUN_DIR": "${RUN_DIR}",
    "CUSTOMER_SERVICE_BUSINESS_NAME": "${BUSINESS_NAME}",
    "CUSTOMER_SERVICE_SCOPE": "${SERVICE_SCOPE}",
    "CUSTOMER_SERVICE_OPENING_MESSAGE": "${OPENING_MESSAGE}",
    "CUSTOMER_SERVICE_ESCALATION_POLICY": "${ESCALATION_POLICY}",
    "CUSTOMER_SERVICE_VOICE": "${VOICE_NAME}",
    "MAGPIE_VOICE": "${VOICE_NAME}",
    "CUSTOMER_SERVICE_KNOWLEDGE_PATH": "${KNOWLEDGE_PATH}",
    "CUSTOMER_SERVICE_PUBLIC_URL": "${VOICE_URL}",
    "CUSTOMER_SERVICE_HEALTH_URL": "${HEALTH_URL}",
    "VOICE_HTTPS_PORT": "${VOICE_PORT}",
    "MN_LLM_PROVIDER": "docker_model_runner",
    "CUSTOMER_SERVICE_STACK_WAIT_SECONDS": "900"
  },
  "config_overrides": {
    "inputs": {
      "payload": {
        "business_name": "${BUSINESS_NAME}",
        "service_scope": "${SERVICE_SCOPE}",
        "opening_message": "${OPENING_MESSAGE}",
        "escalation_policy": "${ESCALATION_POLICY}",
        "voice": "${VOICE_NAME}",
        "voice_https_port": ${VOICE_PORT},
        "voice_local_proxy_port": ${LOCAL_PROXY_PORT},
        "voice_public_url": "${VOICE_URL}"
      }
    },
    "web_ui": {
      "dashboard": {
        "voice_url": "${VOICE_URL}",
        "health_url": "${HEALTH_URL}",
        "knowledge_artifact": "knowledge/customer_service_knowledge.txt",
        "conversation_artifact": "conversation.jsonl"
      }
    }
  }
}
JSON
