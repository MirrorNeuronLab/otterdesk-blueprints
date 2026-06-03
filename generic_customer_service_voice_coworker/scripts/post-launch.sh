#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${MN_RUN_ID:-customer-service-voice-dev}"
RUN_DIR="${MN_RUN_DIR:-$HOME/.mn/runs/${RUN_ID}}"
STATE_FILE="${MN_POST_LAUNCH_STATE_FILE:-${RUN_DIR}/post_launch_state.json}"

if [[ ! -f "${STATE_FILE}" ]]; then
  exit 0
fi

eval "$(
  STATE_FILE="${STATE_FILE}" python3 - <<'PY'
import json
import os
import shlex
from pathlib import Path

state = json.loads(Path(os.environ["STATE_FILE"]).read_text(encoding="utf-8"))
for key in [
    "spark_host",
    "remote_run_dir",
    "voice_port",
    "local_proxy_port",
    "local_proxy_pid",
    "local_proxy_status",
    "voice_url",
    "health_url",
]:
    value = state.get(key) or ""
    print(f"{key.upper()}={shlex.quote(str(value))}")
PY
)"

mkdir -p "${RUN_DIR}/knowledge"

copy_if_exists() {
  local remote_path="$1"
  local local_path="$2"
  if ssh "${SPARK_HOST}" "test -f '${remote_path}'" >/dev/null 2>&1; then
    scp -q "${SPARK_HOST}:${remote_path}" "${local_path}" || true
  fi
}

copy_if_exists "${REMOTE_RUN_DIR}/knowledge/customer_service_knowledge.txt" "${RUN_DIR}/knowledge/customer_service_knowledge.txt"
copy_if_exists "${REMOTE_RUN_DIR}/knowledge/customer_service_knowledge.meta.json" "${RUN_DIR}/knowledge/customer_service_knowledge.meta.json"
copy_if_exists "${REMOTE_RUN_DIR}/conversation.jsonl" "${RUN_DIR}/conversation.jsonl"
copy_if_exists "${REMOTE_RUN_DIR}/voice_service.json" "${RUN_DIR}/voice_service.json"
copy_if_exists "${REMOTE_RUN_DIR}/logs.jsonl" "${RUN_DIR}/logs.jsonl"

if [[ "${LOCAL_PROXY_STATUS:-}" == "started" && -n "${LOCAL_PROXY_PID:-}" && "${LOCAL_PROXY_PID}" =~ ^[0-9]+$ ]]; then
  proxy_cmd="$(ps -p "${LOCAL_PROXY_PID}" -o command= 2>/dev/null || true)"
  if [[ "${proxy_cmd}" == *"ssh"* && "${proxy_cmd}" == *"127.0.0.1:${LOCAL_PROXY_PORT}:127.0.0.1:${VOICE_PORT}"* ]]; then
    kill "${LOCAL_PROXY_PID}" >/dev/null 2>&1 || true
    sleep 1
  fi
fi
rm -f "${RUN_DIR}/voice_proxy.pid"

ssh "${SPARK_HOST}" "RUN_ID='${RUN_ID}' REMOTE_RUN_DIR='${REMOTE_RUN_DIR}' bash -s" <<'SH' || true
set -euo pipefail
pid_file="${REMOTE_RUN_DIR}/voice_service.pid"
if [[ ! -f "${pid_file}" ]]; then
  exit 0
fi
pid="$(cat "${pid_file}" 2>/dev/null || true)"
if [[ -z "${pid}" || ! "${pid}" =~ ^[0-9]+$ ]]; then
  rm -f "${pid_file}"
  exit 0
fi
cmd="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
case "${cmd}" in
  *serve_customer_service_https.py*|*generic_customer_service_voice_coworker*)
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 1
    ;;
esac
rm -f "${pid_file}"
SH

cat > "${RUN_DIR}/final_artifact.json" <<JSON
{
  "type": "customer_service_voice_service",
  "executive_summary": "The Spark-hosted pizza-ordering voice co-worker run has been cleaned up.",
  "recommended_action": "Review the copied knowledge snapshot and conversation artifacts in the local run store.",
  "confidence": 0.85,
  "evidence": [
    {"source": "voice_service.json", "detail": "Voice service metadata was copied back when available."},
    {"source": "knowledge/customer_service_knowledge.txt", "detail": "Latest editable knowledge snapshot was copied back when available."},
    {"source": "conversation.jsonl", "detail": "Conversation turns were copied back when available."}
  ],
  "next_steps": [
    "Review conversation.jsonl for customer turns.",
    "Keep or update the knowledge snapshot before the next run.",
    "Escalate any unresolved customer issues recorded by the co-worker."
  ],
  "source_refs": ["voice_service.json", "knowledge/customer_service_knowledge.txt", "conversation.jsonl", "events.jsonl", "logs.jsonl"]
}
JSON
