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

mkdir -p "${RUN_DIR}" "${RUN_DIR}/knowledge"

eval "$(
  CONFIG_JSON="${CONFIG_JSON}" python3 - <<'PY'
import json
import os
import shlex

config = json.loads(os.environ.get("CONFIG_JSON") or "{}")
payload = ((config.get("inputs") or {}).get("payload") or {})
values = {
    "BUSINESS_NAME": payload.get("business_name") or "Otter Slice Pizza",
    "SERVICE_SCOPE": payload.get("service_scope") or "Take pizza orders from the editable menu knowledge, collect pickup or delivery details, and recommend human handoff when needed.",
    "OPENING_MESSAGE": payload.get("opening_message") or "Thanks for calling Otter Slice Pizza. What delicious trouble can I help you get into today?",
    "ESCALATION_POLICY": payload.get("escalation_policy") or "Escalate allergies, food-safety concerns, refunds, complaints, payment-card questions, missing orders, angry callers, and anything not grounded in the knowledge base.",
    "VOICE_NAME": payload.get("voice") or "aria",
    "SPARK_HOST": payload.get("spark_host") or "homer@spark",
    "SPARK_IP": payload.get("spark_ip") or "192.168.4.173",
    "SPARK_NODE": payload.get("spark_node") or "mn2@192.168.4.173",
    "VOICE_PORT": str(payload.get("voice_https_port") or 7863),
    "LOCAL_PROXY_PORT": str(payload.get("voice_local_proxy_port") or payload.get("local_proxy_port") or payload.get("voice_https_port") or 7863),
    "KNOWLEDGE_TEXT": payload.get("knowledge_text") or "",
}
for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)"

SPARK_VOICE_URL="https://${SPARK_IP}:${VOICE_PORT}/customer-service"
SPARK_HEALTH_URL="https://${SPARK_IP}:${VOICE_PORT}/health"
VOICE_URL="https://localhost:${LOCAL_PROXY_PORT}/customer-service"
HEALTH_URL="https://localhost:${LOCAL_PROXY_PORT}/health"
REMOTE_RUN_DIR="/home/homer/.mn/runs/${RUN_ID}"
REMOTE_KNOWLEDGE_PATH="${REMOTE_RUN_DIR}/knowledge/customer_service_knowledge.txt"
NEMOTRON_ROOT="/home/homer/Sandbox/nemotron-january-2026"
MODEL_NAME="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
PROXY_PID_FILE="${RUN_DIR}/voice_proxy.pid"
PROXY_LOG_FILE="${RUN_DIR}/voice_proxy.log"
LOCAL_PROXY_STATUS="not_started"
LOCAL_PROXY_PID=""

if [[ -z "${KNOWLEDGE_TEXT}" ]]; then
  if [[ -f "${BUNDLE_DIR}/knowledge/default_knowledge.txt" ]]; then
    KNOWLEDGE_TEXT="$(cat "${BUNDLE_DIR}/knowledge/default_knowledge.txt")"
  else
    KNOWLEDGE_TEXT="Generic customer-service knowledge is not configured yet."
  fi
fi

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

append_event "customer_service_voice_prepared" "{\"phase\":\"ssh_check\",\"spark_host\":\"${SPARK_HOST}\"}"

ssh -o BatchMode=yes -o ConnectTimeout=8 "${SPARK_HOST}" "test -d '${NEMOTRON_ROOT}' && nvidia-smi >/dev/null"
ssh "${SPARK_HOST}" "mkdir -p '${REMOTE_RUN_DIR}/knowledge' '${REMOTE_RUN_DIR}/certs'"

LOCAL_SEED="${RUN_DIR}/knowledge/customer_service_knowledge.txt"
printf "%s\n" "${KNOWLEDGE_TEXT}" > "${LOCAL_SEED}"
scp -q "${LOCAL_SEED}" "${SPARK_HOST}:${REMOTE_KNOWLEDGE_PATH}"

ssh "${SPARK_HOST}" "cd '${NEMOTRON_ROOT}' && if ! scripts/nemotron.sh status | grep -qi running; then scripts/nemotron.sh start --mode vllm; fi"

wait_remote_http() {
  local name="$1"
  local url="$2"
  local timeout="${3:-25}"
  local deadline=$((SECONDS + timeout))
  until ssh "${SPARK_HOST}" "curl -fsS --max-time 2 '${url}' >/dev/null" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 2
  done
}

local_port_listener_pid() {
  lsof -nP -t -iTCP:"${LOCAL_PROXY_PORT}" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

stop_owned_local_proxy() {
  if [[ ! -f "${PROXY_PID_FILE}" ]]; then
    return 0
  fi
  local old_pid
  old_pid="$(cat "${PROXY_PID_FILE}" 2>/dev/null || true)"
  if [[ -z "${old_pid}" || ! "${old_pid}" =~ ^[0-9]+$ ]]; then
    rm -f "${PROXY_PID_FILE}"
    return 0
  fi
  local cmd
  cmd="$(ps -p "${old_pid}" -o command= 2>/dev/null || true)"
  if [[ "${cmd}" == *"ssh"* && "${cmd}" == *"127.0.0.1:${LOCAL_PROXY_PORT}:127.0.0.1:${VOICE_PORT}"* ]]; then
    kill "${old_pid}" >/dev/null 2>&1 || true
    sleep 1
  fi
  rm -f "${PROXY_PID_FILE}"
}

start_local_voice_proxy() {
  local existing_pid existing_cmd
  existing_pid="$(local_port_listener_pid)"
  if [[ -n "${existing_pid}" ]]; then
    existing_cmd="$(ps -p "${existing_pid}" -o command= 2>/dev/null || true)"
    if [[ "${existing_cmd}" == *"ssh"* && "${existing_cmd}" == *"127.0.0.1:${LOCAL_PROXY_PORT}:127.0.0.1:${VOICE_PORT}"* ]]; then
      LOCAL_PROXY_STATUS="reused"
      LOCAL_PROXY_PID="${existing_pid}"
      echo "${existing_pid}" > "${PROXY_PID_FILE}"
      return 0
    fi
    echo "Local port ${LOCAL_PROXY_PORT} is already in use by PID ${existing_pid}; cannot create customer voice localhost proxy." >&2
    echo "Command: ${existing_cmd}" >&2
    return 1
  fi

  stop_owned_local_proxy
  : > "${PROXY_LOG_FILE}"
  nohup ssh \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -N \
    -L "127.0.0.1:${LOCAL_PROXY_PORT}:127.0.0.1:${VOICE_PORT}" \
    "${SPARK_HOST}" >"${PROXY_LOG_FILE}" 2>&1 < /dev/null &
  LOCAL_PROXY_PID="$!"
  sleep 1
  if ! kill -0 "${LOCAL_PROXY_PID}" >/dev/null 2>&1; then
    echo "Failed to start localhost proxy for Spark voice service." >&2
    cat "${PROXY_LOG_FILE}" >&2 || true
    return 1
  fi
  echo "${LOCAL_PROXY_PID}" > "${PROXY_PID_FILE}"
  LOCAL_PROXY_STATUS="started"
}

STACK_STATUS="ready"
WAIT_SECONDS="${NEMOTRON_PRELAUNCH_WAIT_SECONDS:-25}"
if ! wait_remote_http "NVIDIA ASR" "http://127.0.0.1:8080/health" "${WAIT_SECONDS}"; then
  STACK_STATUS="starting"
fi
if [[ "${STACK_STATUS}" == "ready" ]] && ! wait_remote_http "Nemotron vLLM" "http://127.0.0.1:8000/health" "${WAIT_SECONDS}"; then
  STACK_STATUS="starting"
fi
if [[ "${STACK_STATUS}" == "ready" ]] && ! wait_remote_http "Magpie TTS" "http://127.0.0.1:8001/health" "${WAIT_SECONDS}"; then
  STACK_STATUS="starting"
fi

if [[ "${STACK_STATUS}" != "ready" && "${CUSTOMER_SERVICE_PRELAUNCH_STRICT_HEALTH:-0}" == "1" ]]; then
  echo "NVIDIA stack did not become healthy during pre-launch." >&2
  exit 1
fi

append_event "customer_service_voice_stack_ready" "{\"status\":\"${STACK_STATUS}\",\"spark_host\":\"${SPARK_HOST}\"}"
start_local_voice_proxy
append_event "customer_service_voice_proxy_ready" "{\"status\":\"${LOCAL_PROXY_STATUS}\",\"pid\":\"${LOCAL_PROXY_PID}\",\"local_url\":\"${VOICE_URL}\",\"spark_url\":\"${SPARK_VOICE_URL}\"}"

cat > "${STATE_FILE}" <<JSON
{
  "schema_version": "mn.blueprint.customer_service_voice.pre_launch_state.v1",
  "run_id": "${RUN_ID}",
  "spark_host": "${SPARK_HOST}",
  "spark_ip": "${SPARK_IP}",
  "spark_node": "${SPARK_NODE}",
  "voice_port": ${VOICE_PORT},
  "local_proxy_port": ${LOCAL_PROXY_PORT},
  "local_proxy_pid": "${LOCAL_PROXY_PID}",
  "local_proxy_status": "${LOCAL_PROXY_STATUS}",
  "voice_url": "${VOICE_URL}",
  "health_url": "${HEALTH_URL}",
  "spark_voice_url": "${SPARK_VOICE_URL}",
  "spark_health_url": "${SPARK_HEALTH_URL}",
  "remote_run_dir": "${REMOTE_RUN_DIR}",
  "remote_knowledge_path": "${REMOTE_KNOWLEDGE_PATH}",
  "stack_status": "${STACK_STATUS}"
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
  "spark_host": "${SPARK_HOST}",
  "spark_voice_url": "${SPARK_VOICE_URL}",
  "proxy_status": "${LOCAL_PROXY_STATUS}",
  "knowledge_path": "knowledge/customer_service_knowledge.txt",
  "conversation_path": "conversation.jsonl",
  "status": "${STACK_STATUS}"
}
JSON

cat > "${RUN_DIR}/voice_service.json" <<JSON
{
  "schema_version": "mn.blueprint.voice_service.v1",
  "blueprint_id": "generic_customer_service_voice_coworker",
  "run_id": "${RUN_ID}",
  "public_url": "${VOICE_URL}",
  "health_url": "${HEALTH_URL}",
  "spark_url": "${SPARK_VOICE_URL}",
  "proxy_status": "${LOCAL_PROXY_STATUS}",
  "remote_run_dir": "${REMOTE_RUN_DIR}",
  "knowledge_path": "${REMOTE_KNOWLEDGE_PATH}",
  "status": "pre_launch_${STACK_STATUS}"
}
JSON

cat > "${RUN_DIR}/final_artifact.json" <<JSON
{
  "type": "customer_service_voice_service",
  "executive_summary": "The pizza-ordering voice co-worker is prepared for Spark launch through a localhost proxy.",
  "recommended_action": "Open ${VOICE_URL} after the runtime voice node starts.",
  "confidence": 0.75,
  "evidence": [
    {"source": "pre_launch.ready", "detail": "Spark pre-launch prepared the run-scoped knowledge file."},
    {"source": "voice_service.json", "detail": "Localhost voice URL, Spark backend URL, and health URL were recorded."}
  ],
  "next_steps": [
    "Confirm the Spark node is part of the cluster with profile customer-service-voice-nvidia.",
    "Start the blueprint runtime.",
    "Open the localhost voice URL and test microphone conversation."
  ],
  "source_refs": ["web_ui.json", "voice_service.json", "knowledge/customer_service_knowledge.txt", "events.jsonl"]
}
JSON

cat > "${READY_FILE}" <<JSON
{
  "env": {
    "CUSTOMER_SERVICE_RUN_ID": "${RUN_ID}",
    "CUSTOMER_SERVICE_BUSINESS_NAME": "${BUSINESS_NAME}",
    "CUSTOMER_SERVICE_SCOPE": "${SERVICE_SCOPE}",
    "CUSTOMER_SERVICE_OPENING_MESSAGE": "${OPENING_MESSAGE}",
    "CUSTOMER_SERVICE_ESCALATION_POLICY": "${ESCALATION_POLICY}",
    "CUSTOMER_SERVICE_VOICE": "${VOICE_NAME}",
    "MAGPIE_VOICE": "${VOICE_NAME}",
    "CUSTOMER_SERVICE_SPARK_HOST": "${SPARK_HOST}",
    "CUSTOMER_SERVICE_SPARK_IP": "${SPARK_IP}",
    "CUSTOMER_SERVICE_SPARK_PUBLIC_URL": "${SPARK_VOICE_URL}",
    "CUSTOMER_SERVICE_LOCAL_PROXY_PORT": "${LOCAL_PROXY_PORT}",
    "CUSTOMER_SERVICE_RUN_DIR": "${REMOTE_RUN_DIR}",
    "CUSTOMER_SERVICE_KNOWLEDGE_PATH": "${REMOTE_KNOWLEDGE_PATH}",
    "CUSTOMER_SERVICE_PUBLIC_URL": "${VOICE_URL}",
    "CUSTOMER_SERVICE_HEALTH_URL": "${HEALTH_URL}",
    "VOICE_HTTPS_PORT": "${VOICE_PORT}",
    "NEMOTRON_ROOT": "${NEMOTRON_ROOT}",
    "NVIDIA_ASR_URL": "ws://${SPARK_IP}:8080",
    "NVIDIA_ASR_HEALTH_URL": "http://${SPARK_IP}:8080/health",
    "NVIDIA_LLM_URL": "http://${SPARK_IP}:8000/v1",
    "NVIDIA_LLM_HEALTH_URL": "http://${SPARK_IP}:8000/health",
    "NVIDIA_LLM_MODEL": "${MODEL_NAME}",
    "NVIDIA_TTS_URL": "http://${SPARK_IP}:8001",
    "NVIDIA_TTS_HEALTH_URL": "http://${SPARK_IP}:8001/health",
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
        "spark_host": "${SPARK_HOST}",
        "spark_node": "${SPARK_NODE}",
        "spark_ip": "${SPARK_IP}",
        "voice_https_port": ${VOICE_PORT},
        "voice_local_proxy_port": ${LOCAL_PROXY_PORT},
        "voice_public_url": "${VOICE_URL}"
      }
    },
    "web_ui": {
      "dashboard": {
        "voice_url": "${VOICE_URL}",
        "spark_voice_url": "${SPARK_VOICE_URL}",
        "spark_health_url": "${HEALTH_URL}",
        "knowledge_artifact": "knowledge/customer_service_knowledge.txt",
        "conversation_artifact": "conversation.jsonl"
      }
    }
  }
}
JSON
