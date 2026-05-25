#!/usr/bin/env bash
set -euo pipefail

MN_RUN_DIR="${MN_RUN_DIR:-}"
MN_POST_LAUNCH_STATE_FILE="${MN_POST_LAUNCH_STATE_FILE:-}"
MN_PRE_LAUNCH_READY_FILE="${MN_PRE_LAUNCH_READY_FILE:-}"
MN_POST_LAUNCH_REASON="${MN_POST_LAUNCH_REASON:-post_launch}"

if [[ -z "$MN_POST_LAUNCH_STATE_FILE" && -n "$MN_RUN_DIR" ]]; then
  MN_POST_LAUNCH_STATE_FILE="${MN_RUN_DIR}/post_launch_state.json"
fi
if [[ -z "$MN_PRE_LAUNCH_READY_FILE" && -n "$MN_RUN_DIR" ]]; then
  MN_PRE_LAUNCH_READY_FILE="${MN_RUN_DIR}/pre_launch.ready"
fi

state_field() {
  local field="$1"
  if [[ -z "$MN_POST_LAUNCH_STATE_FILE" || ! -f "$MN_POST_LAUNCH_STATE_FILE" ]]; then
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  python3 - "$MN_POST_LAUNCH_STATE_FILE" "$field" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
field = sys.argv[2]
try:
    value = json.loads(path.read_text()).get(field, "")
except Exception:
    value = ""
if value is None:
    value = ""
print(value)
PY
}

process_field() {
  local field="$1"
  if [[ -z "${MN_PRE_LAUNCH_PROCESS_FILE:-}" || ! -f "$MN_PRE_LAUNCH_PROCESS_FILE" ]]; then
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  python3 - "$MN_PRE_LAUNCH_PROCESS_FILE" "$field" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
field = sys.argv[2]
try:
    value = json.loads(path.read_text()).get(field, "")
except Exception:
    value = ""
if value is None:
    value = ""
print(value)
PY
}

ready_env_field() {
  local field="$1"
  if [[ -z "$MN_PRE_LAUNCH_READY_FILE" || ! -f "$MN_PRE_LAUNCH_READY_FILE" ]]; then
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  python3 - "$MN_PRE_LAUNCH_READY_FILE" "$field" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
field = sys.argv[2]
try:
    value = (json.loads(path.read_text()).get("env") or {}).get(field, "")
except Exception:
    value = ""
if value is None:
    value = ""
print(value)
PY
}

SERVER_PID="${SERVER_PID:-$(state_field server_pid)}"
PUBLISHER_PID="${PUBLISHER_PID:-$(state_field publisher_pid)}"
RTSP_PORT="${RTSP_PORT:-$(ready_env_field RTSP_PORT)}"
RTSP_PORT="${RTSP_PORT:-$(state_field rtsp_port)}"
RTSP_PORT="${RTSP_PORT:-8554}"
WEBRTC_PORT="${WEBRTC_PORT:-$(ready_env_field WEBRTC_PORT)}"
WEBRTC_PORT="${WEBRTC_PORT:-$(state_field webrtc_port)}"
WEBRTC_PORT="${WEBRTC_PORT:-8889}"
WEBRTC_LOCAL_TCP_PORT="${WEBRTC_LOCAL_TCP_PORT:-$(ready_env_field WEBRTC_LOCAL_TCP_PORT)}"
WEBRTC_LOCAL_TCP_PORT="${WEBRTC_LOCAL_TCP_PORT:-$(state_field webrtc_local_tcp_port)}"
WEBRTC_LOCAL_TCP_PORT="${WEBRTC_LOCAL_TCP_PORT:-8189}"
CONFIG_DIR="${CONFIG_DIR:-$(state_field config_dir)}"
PRE_LAUNCH_PID="${MN_PRE_LAUNCH_PID:-$(process_field pid)}"
PRE_LAUNCH_PROCESS_GROUP_ID="${MN_PRE_LAUNCH_PROCESS_GROUP_ID:-$(process_field process_group_id)}"

is_integer() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

current_process_group_id() {
  ps -p "$$" -o pgid= 2>/dev/null | tr -d '[:space:]' || true
}

process_command() {
  local pid="$1"
  local command_line=""
  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  if [[ -n "$command_line" ]]; then
    printf '%s\n' "$command_line"
    return 0
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -p "$pid" 2>/dev/null | awk 'NR == 2 { print $1; exit }' || true
  fi
}

process_group_exists() {
  local pgid="$1"
  if ! is_integer "$pgid"; then
    return 1
  fi
  kill -0 -- "-$pgid" >/dev/null 2>&1
}

terminate_process_group() {
  local pgid="$1"
  local label="$2"
  if ! is_integer "$pgid" || [[ "$pgid" == "1" ]]; then
    return 0
  fi
  local current_pgid
  current_pgid="$(current_process_group_id)"
  if [[ -n "$current_pgid" && "$pgid" == "$current_pgid" ]]; then
    echo "Skipping ${label} process group ${pgid}; it is the cleanup script's current process group."
    return 0
  fi
  if ! process_group_exists "$pgid"; then
    return 0
  fi

  echo "Stopping ${label} process group ${pgid} for ${MN_POST_LAUNCH_REASON}."
  kill -TERM -- "-$pgid" >/dev/null 2>&1 || true
  for _ in {1..30}; do
    if ! process_group_exists "$pgid"; then
      return 0
    fi
    sleep 0.1
  done
  kill -KILL -- "-$pgid" >/dev/null 2>&1 || true
  for _ in {1..30}; do
    if ! process_group_exists "$pgid"; then
      return 0
    fi
    sleep 0.1
  done
}

is_expected_mapper_pid() {
  local pid="$1"
  local command
  command="$(process_command "$pid")"
  case "$command" in
    *mediamtx*|*rtsp-simple-server*|*ffmpeg*|*pre-launch.sh*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

terminate_pid() {
  local pid="$1"
  local label="$2"
  if ! is_integer "$pid"; then
    return 0
  fi
  local process_exists="false"
  if kill -0 "$pid" >/dev/null 2>&1; then
    process_exists="true"
  elif command -v lsof >/dev/null 2>&1 && lsof -nP -p "$pid" >/dev/null 2>&1; then
    process_exists="true"
  fi
  if [[ "$process_exists" != "true" ]]; then
    return 0
  fi
  if ! is_expected_mapper_pid "$pid"; then
    echo "Skipping ${label} PID ${pid}; command does not look like this blueprint's mapper: $(process_command "$pid")"
    return 0
  fi

  echo "Stopping ${label} PID ${pid} for ${MN_POST_LAUNCH_REASON}."
  if ! kill "$pid" >/dev/null 2>&1; then
    if kill -0 "$pid" >/dev/null 2>&1 || { command -v lsof >/dev/null 2>&1 && lsof -nP -p "$pid" >/dev/null 2>&1; }; then
      echo "Could not stop ${label} PID ${pid}; permission may be restricted."
    fi
    return 0
  fi
  for _ in {1..30}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  kill -9 "$pid" >/dev/null 2>&1 || true
}

port_listener_pids() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
  fi
}

terminate_mediamtx_on_port() {
  local port="$1"
  local label="$2"
  if [[ -z "$port" ]]; then
    return 0
  fi
  local pid
  while IFS= read -r pid; do
    if [[ -z "$pid" ]]; then
      continue
    fi
    case "$(process_command "$pid")" in
      *mediamtx*|*rtsp-simple-server*)
        terminate_pid "$pid" "${label} listener on ${port}"
        ;;
      *)
        echo "Port ${port} is owned by PID ${pid}, not MediaMTX; leaving it alone."
        ;;
    esac
  done < <(port_listener_pids "$port")
}

terminate_pid "$PUBLISHER_PID" "ffmpeg demo publisher"
terminate_pid "$SERVER_PID" "MediaMTX demo server"
terminate_mediamtx_on_port "$RTSP_PORT" "RTSP"
terminate_mediamtx_on_port "$WEBRTC_PORT" "browser preview"
terminate_mediamtx_on_port "$WEBRTC_LOCAL_TCP_PORT" "WebRTC TCP"
terminate_process_group "$PRE_LAUNCH_PROCESS_GROUP_ID" "pre-launch hook"
terminate_pid "$PRE_LAUNCH_PID" "pre-launch hook"

if [[ -n "$CONFIG_DIR" ]]; then
  case "$CONFIG_DIR" in
    /tmp/video_watch_assistant_mediamtx.*)
      rm -rf "$CONFIG_DIR"
      ;;
    *)
      echo "Skipping config cleanup outside expected temp prefix: ${CONFIG_DIR}"
      ;;
  esac
fi

if [[ -n "$MN_POST_LAUNCH_STATE_FILE" ]]; then
  rm -f "$MN_POST_LAUNCH_STATE_FILE"
fi

echo "Video Watch Assistant post-launch cleanup complete."
