#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${MN_RUN_ID:-customer-service-voice-dev}"
RUN_DIR="${MN_RUN_DIR:-$HOME/.mn/runs/${RUN_ID}}"
STATE_FILE="${MN_POST_LAUNCH_STATE_FILE:-${RUN_DIR}/post_launch_state.json}"
CLEANUP_REASON="${MN_POST_LAUNCH_REASON:-unknown}"

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
    "profile_keeper_pid",
    "profile_keeper_status",
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
    "source": "customer_service_post_launch",
}
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY
}

service_is_healthy() {
  [[ -n "${HEALTH_URL:-}" ]] || return 1
  curl -kfsS --max-time 3 "${HEALTH_URL}" >/dev/null 2>&1
}

if [[ "${CLEANUP_REASON}" == "job_failed" ]] && service_is_healthy; then
  append_event "customer_service_voice_cleanup_deferred" "{\"reason\":\"${CLEANUP_REASON}\",\"health_url\":\"${HEALTH_URL}\",\"voice_url\":\"${VOICE_URL}\"}"
  cat > "${RUN_DIR}/final_artifact.json" <<JSON
{
  "type": "customer_service_voice_service",
  "executive_summary": "The Spark-hosted pizza-ordering voice co-worker is still healthy, so cleanup was deferred after a runtime bookkeeping failure.",
  "recommended_action": "Keep using ${VOICE_URL}; cancel the run when you are ready to stop the voice line.",
  "confidence": 0.8,
  "evidence": [
    {"source": "health_url", "detail": "${HEALTH_URL} responded during post-launch cleanup."},
    {"source": "voice_service.json", "detail": "Voice service metadata was copied back when available."},
    {"source": "knowledge/customer_service_knowledge.txt", "detail": "Latest editable knowledge snapshot was copied back when available."}
  ],
  "next_steps": [
    "Open ${VOICE_URL} to continue testing the call page.",
    "Use the knowledge editor on the call page for menu changes.",
    "Cancel the run when finished to remove the localhost proxy and Spark voice process."
  ],
  "source_refs": ["voice_service.json", "knowledge/customer_service_knowledge.txt", "conversation.jsonl", "events.jsonl", "logs.jsonl"]
}
JSON
  exit 0
fi

if [[ "${LOCAL_PROXY_STATUS:-}" == "started" && -n "${LOCAL_PROXY_PID:-}" && "${LOCAL_PROXY_PID}" =~ ^[0-9]+$ ]]; then
  proxy_cmd="$(ps -p "${LOCAL_PROXY_PID}" -o command= 2>/dev/null || true)"
  if [[ "${proxy_cmd}" == *"ssh"* && "${proxy_cmd}" == *"127.0.0.1:${LOCAL_PROXY_PORT}:127.0.0.1:${VOICE_PORT}"* ]]; then
    kill "${LOCAL_PROXY_PID}" >/dev/null 2>&1 || true
    sleep 1
  fi
fi
rm -f "${RUN_DIR}/voice_proxy.pid"

if [[ "${PROFILE_KEEPER_STATUS:-}" == "started" && -n "${PROFILE_KEEPER_PID:-}" && "${PROFILE_KEEPER_PID}" =~ ^[0-9]+$ ]]; then
  keeper_cmd="$(ps -p "${PROFILE_KEEPER_PID}" -o command= 2>/dev/null || true)"
  if [[ "${keeper_cmd}" == *"CUSTOMER_SERVICE_SPARK_NODE"* || "${keeper_cmd}" == *"mirror-neuron-redis"* ]]; then
    kill "${PROFILE_KEEPER_PID}" >/dev/null 2>&1 || true
    sleep 1
  fi
fi
rm -f "${RUN_DIR}/spark_profile_keeper.pid"

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
