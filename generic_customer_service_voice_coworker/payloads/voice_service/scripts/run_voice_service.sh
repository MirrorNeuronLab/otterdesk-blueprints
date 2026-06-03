#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOICE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RUN_ID="${CUSTOMER_SERVICE_RUN_ID:-${MN_RUN_ID:-customer-service-voice-dev}}"
RUN_DIR="${CUSTOMER_SERVICE_RUN_DIR:-${MN_RUN_DIR:-$HOME/.mn/runs/${RUN_ID}}}"
SPARK_IP="${CUSTOMER_SERVICE_SPARK_IP:-192.168.4.173}"
VOICE_PORT="${VOICE_HTTPS_PORT:-7863}"
PUBLIC_URL="${CUSTOMER_SERVICE_PUBLIC_URL:-https://${SPARK_IP}:${VOICE_PORT}/customer-service}"
HEALTH_URL="${CUSTOMER_SERVICE_HEALTH_URL:-https://${SPARK_IP}:${VOICE_PORT}/health}"
KNOWLEDGE_PATH="${CUSTOMER_SERVICE_KNOWLEDGE_PATH:-${RUN_DIR}/knowledge/customer_service_knowledge.txt}"
CERT_DIR="${RUN_DIR}/certs"
CERT_FILE="${NEMOTRON_SSL_CERT:-${CERT_DIR}/customer-service.crt}"
KEY_FILE="${NEMOTRON_SSL_KEY:-${CERT_DIR}/customer-service.key}"
PID_FILE="${RUN_DIR}/voice_service.pid"
LOG_FILE="${RUN_DIR}/voice_service.log"

export CUSTOMER_SERVICE_RUN_ID="${RUN_ID}"
export CUSTOMER_SERVICE_RUN_DIR="${RUN_DIR}"
export CUSTOMER_SERVICE_PUBLIC_URL="${PUBLIC_URL}"
export CUSTOMER_SERVICE_HEALTH_URL="${HEALTH_URL}"
export CUSTOMER_SERVICE_KNOWLEDGE_PATH="${KNOWLEDGE_PATH}"
export NEMOTRON_BOT_HOST="${NEMOTRON_BOT_HOST:-0.0.0.0}"
export NEMOTRON_BOT_PORT="${VOICE_PORT}"
export NEMOTRON_SSL_CERT="${CERT_FILE}"
export NEMOTRON_SSL_KEY="${KEY_FILE}"
NVIDIA_HOST="${CUSTOMER_SERVICE_NVIDIA_HOST:-${CUSTOMER_SERVICE_SPARK_IP:-127.0.0.1}}"
export NVIDIA_ASR_URL="${NVIDIA_ASR_URL:-ws://${NVIDIA_HOST}:8080}"
export NVIDIA_LLM_URL="${NVIDIA_LLM_URL:-http://${NVIDIA_HOST}:8000/v1}"
export NVIDIA_LLM_MODEL="${NVIDIA_LLM_MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"
export NVIDIA_TTS_URL="${NVIDIA_TTS_URL:-http://${NVIDIA_HOST}:8001}"
export NEMOTRON_ROOT="${NEMOTRON_ROOT:-/home/homer/Sandbox/nemotron-january-2026}"
if [[ -x "${NEMOTRON_ROOT}/.venv/bin/python" ]]; then
  export CUSTOMER_SERVICE_PYTHON="${CUSTOMER_SERVICE_PYTHON:-${NEMOTRON_ROOT}/.venv/bin/python}"
else
  export CUSTOMER_SERVICE_PYTHON="${CUSTOMER_SERVICE_PYTHON:-python3}"
fi
export PYTHONPATH="${VOICE_ROOT}:${NEMOTRON_ROOT}/pipecat_bots:${PYTHONPATH:-}"

mkdir -p "${RUN_DIR}/knowledge" "${CERT_DIR}"

if [[ ! -s "${KNOWLEDGE_PATH}" ]]; then
  if [[ -n "${CUSTOMER_SERVICE_KNOWLEDGE_TEXT:-}" ]]; then
    printf "%s\n" "${CUSTOMER_SERVICE_KNOWLEDGE_TEXT}" > "${KNOWLEDGE_PATH}"
  elif [[ -f "${VOICE_ROOT}/knowledge/default_knowledge.txt" ]]; then
    cp "${VOICE_ROOT}/knowledge/default_knowledge.txt" "${KNOWLEDGE_PATH}"
  else
    printf "Otter Slice Pizza knowledge is not configured yet. Ask a human before taking a real order.\n" > "${KNOWLEDGE_PATH}"
  fi
fi

if [[ ! -s "${CERT_FILE}" || ! -s "${KEY_FILE}" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "${KEY_FILE}" \
    -out "${CERT_FILE}" \
    -days 365 \
    -subj "/CN=${SPARK_IP}" \
    -addext "subjectAltName=IP:${SPARK_IP},DNS:spark,DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
fi

write_jsonl() {
  local path="$1"
  local event_type="$2"
  local payload="$3"
  "${CUSTOMER_SERVICE_PYTHON}" - "$path" "$event_type" "$payload" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
record = {
    "type": sys.argv[2],
    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "payload": json.loads(sys.argv[3]),
    "source": "customer_service_voice_runner",
}
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY
}

wait_http() {
  local name="$1"
  local url="$2"
  local timeout="${3:-900}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${name} at ${url}" >&2
      return 1
    fi
    sleep 2
  done
}

terminate_owned_voice_process() {
  if [[ ! -f "${PID_FILE}" ]]; then
    return 0
  fi
  local old_pid
  old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -z "${old_pid}" || ! "${old_pid}" =~ ^[0-9]+$ ]]; then
    rm -f "${PID_FILE}"
    return 0
  fi
  local cmd
  cmd="$(ps -p "${old_pid}" -o command= 2>/dev/null || true)"
  if [[ "${cmd}" == *"serve_customer_service_https.py"* ]]; then
    kill "${old_pid}" >/dev/null 2>&1 || true
    sleep 1
  fi
  rm -f "${PID_FILE}"
}

STACK_WAIT_SECONDS="${CUSTOMER_SERVICE_STACK_WAIT_SECONDS:-900}"
wait_http "NVIDIA ASR" "${NVIDIA_ASR_HEALTH_URL:-http://${NVIDIA_HOST}:8080/health}" "${STACK_WAIT_SECONDS}"
wait_http "Nemotron vLLM" "${NVIDIA_LLM_HEALTH_URL:-http://${NVIDIA_HOST}:8000/health}" "${STACK_WAIT_SECONDS}"
wait_http "Magpie TTS" "${NVIDIA_TTS_HEALTH_URL:-http://${NVIDIA_HOST}:8001/health}" "${STACK_WAIT_SECONDS}"

terminate_owned_voice_process

cat > "${RUN_DIR}/voice_service.json" <<JSON
{
  "schema_version": "mn.blueprint.voice_service.v1",
  "blueprint_id": "generic_customer_service_voice_coworker",
  "run_id": "${RUN_ID}",
  "public_url": "${PUBLIC_URL}",
  "health_url": "${HEALTH_URL}",
  "knowledge_path": "${KNOWLEDGE_PATH}",
  "conversation_path": "${RUN_DIR}/conversation.jsonl",
  "events_path": "${RUN_DIR}/events.jsonl",
  "status": "starting"
}
JSON

cat > "${RUN_DIR}/final_artifact.json" <<JSON
{
  "type": "customer_service_voice_service",
  "executive_summary": "The Spark-hosted pizza-ordering voice co-worker is starting behind the localhost proxy.",
  "recommended_action": "Open ${PUBLIC_URL} and test a customer call.",
  "confidence": 0.8,
  "evidence": [
    {"source": "voice_service.json", "detail": "Voice service handle created."},
    {"source": "knowledge/customer_service_knowledge.txt", "detail": "Editable knowledge file prepared."}
  ],
  "next_steps": [
    "Allow microphone access in the browser.",
    "Ask a question grounded in the knowledge text.",
    "Edit and save knowledge, then ask again to confirm retrieval changed."
  ],
  "source_refs": ["voice_service.json", "knowledge/customer_service_knowledge.txt", "events.jsonl", "conversation.jsonl"]
}
JSON

write_jsonl "${RUN_DIR}/events.jsonl" "customer_service_voice_stack_ready" "{\"asr\":\"${NVIDIA_ASR_URL}\",\"llm\":\"${NVIDIA_LLM_URL}\",\"tts\":\"${NVIDIA_TTS_URL}\"}"

"${CUSTOMER_SERVICE_PYTHON}" "${VOICE_ROOT}/serve_customer_service_https.py" >> "${LOG_FILE}" 2>&1 &
server_pid="$!"
echo "${server_pid}" > "${PID_FILE}"
write_jsonl "${RUN_DIR}/events.jsonl" "customer_service_voice_ready" "{\"pid\":${server_pid},\"public_url\":\"${PUBLIC_URL}\"}"
wait "${server_pid}"
