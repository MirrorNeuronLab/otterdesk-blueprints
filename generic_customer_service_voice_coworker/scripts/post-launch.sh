#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${MN_RUN_ID:-customer-service-voice-dev}"
RUN_DIR="${MN_RUN_DIR:-$HOME/.mn/runs/${RUN_ID}}"
STATE_FILE="${MN_POST_LAUNCH_STATE_FILE:-${RUN_DIR}/post_launch_state.json}"
CLEANUP_REASON="${MN_POST_LAUNCH_REASON:-unknown}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

VOICE_URL=""
HEALTH_URL=""
if [[ -f "${STATE_FILE}" ]]; then
  eval "$(
    STATE_FILE="${STATE_FILE}" "${PYTHON_BIN}" - <<'PY'
import json
import os
import shlex
from pathlib import Path

try:
    state = json.loads(Path(os.environ["STATE_FILE"]).read_text(encoding="utf-8"))
except Exception:
    state = {}
for key in ["voice_url", "health_url"]:
    print(f"{key.upper()}={shlex.quote(str(state.get(key) or ''))}")
PY
  )"
fi

mkdir -p "${RUN_DIR}/knowledge"

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
  CLEANUP_DEFERRED_PAYLOAD="$(
    CLEANUP_REASON="${CLEANUP_REASON}" HEALTH_URL="${HEALTH_URL}" VOICE_URL="${VOICE_URL}" "${PYTHON_BIN}" - <<'PY'
import json
import os

print(json.dumps({
    "reason": os.environ["CLEANUP_REASON"],
    "health_url": os.environ["HEALTH_URL"],
    "voice_url": os.environ["VOICE_URL"],
}))
PY
  )"
  append_event "customer_service_voice_cleanup_deferred" "${CLEANUP_DEFERRED_PAYLOAD}"
  RUN_DIR="${RUN_DIR}" VOICE_URL="${VOICE_URL}" HEALTH_URL="${HEALTH_URL}" "${PYTHON_BIN}" - <<'PY'
import json
import os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
voice_url = os.environ["VOICE_URL"]
health_url = os.environ["HEALTH_URL"]
payload = {
    "type": "customer_service_voice_service",
    "executive_summary": "The pizza-ordering voice co-worker is still healthy, so cleanup was deferred after a runtime bookkeeping failure.",
    "recommended_action": f"Keep using {voice_url}; cancel the run when you are ready to stop the voice line.",
    "confidence": 0.8,
    "evidence": [
        {"source": "health_url", "detail": f"{health_url} responded during post-launch cleanup."},
        {"source": "voice_service.json", "detail": "Voice service metadata is available when the runtime node wrote it."},
        {"source": "knowledge/customer_service_knowledge.txt", "detail": "Run-scoped editable knowledge is available."},
    ],
    "next_steps": [
        f"Open {voice_url} to continue testing the call page.",
        "Use the knowledge editor on the call page for menu changes.",
        "Cancel the run when finished to remove the runtime voice process.",
    ],
    "source_refs": ["voice_service.json", "knowledge/customer_service_knowledge.txt", "conversation.jsonl", "events.jsonl", "logs.jsonl"],
}
(run_dir / "final_artifact.json").write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
PY
  exit 0
fi

PID_FILE="${RUN_DIR}/voice_service.pid"
if [[ -f "${PID_FILE}" ]]; then
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${pid}" && "${pid}" =~ ^[0-9]+$ ]]; then
    cmd="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
    case "${cmd}" in
      *serve_customer_service_https.py*|*generic_customer_service_voice_coworker*)
        kill "${pid}" >/dev/null 2>&1 || true
        sleep 1
        ;;
    esac
  fi
  rm -f "${PID_FILE}"
fi

RUN_DIR="${RUN_DIR}" "${PYTHON_BIN}" - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "type": "customer_service_voice_service",
    "executive_summary": "The pizza-ordering voice co-worker run has been cleaned up.",
    "recommended_action": "Review the knowledge snapshot and conversation artifacts in the run store.",
    "confidence": 0.85,
    "evidence": [
        {"source": "voice_service.json", "detail": "Voice service metadata is available when the runtime node wrote it."},
        {"source": "knowledge/customer_service_knowledge.txt", "detail": "Latest editable knowledge snapshot is in the run store."},
        {"source": "conversation.jsonl", "detail": "Conversation turns are available when a session occurred."},
    ],
    "next_steps": [
        "Review conversation.jsonl for customer turns.",
        "Keep or update the knowledge snapshot before the next run.",
        "Escalate any unresolved customer issues recorded by the co-worker.",
    ],
    "source_refs": ["voice_service.json", "knowledge/customer_service_knowledge.txt", "conversation.jsonl", "events.jsonl", "logs.jsonl"],
}
target = Path(os.environ["RUN_DIR"]) / "final_artifact.json"
target.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
PY

CLEANUP_COMPLETED_PAYLOAD="$(
  CLEANUP_REASON="${CLEANUP_REASON}" VOICE_URL="${VOICE_URL}" "${PYTHON_BIN}" - <<'PY'
import json
import os

print(json.dumps({
    "reason": os.environ["CLEANUP_REASON"],
    "voice_url": os.environ["VOICE_URL"],
}))
PY
)"
append_event "customer_service_voice_cleanup_completed" "${CLEANUP_COMPLETED_PAYLOAD}"
