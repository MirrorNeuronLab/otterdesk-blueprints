#!/usr/bin/env bash
set -euo pipefail

RTSP_PORT="${RTSP_PORT:-8554}"
STREAM_PATH="${STREAM_PATH:-video-watch}"
STREAM_URI_OVERRIDE="${STREAM_URI:-}"
STREAM_URI="${STREAM_URI_OVERRIDE:-rtsp://127.0.0.1:${RTSP_PORT}/${STREAM_PATH}}"
BROWSER_PREVIEW_URI_OVERRIDE="${BROWSER_PREVIEW_URI:-}"
WEBRTC_PORT="${WEBRTC_PORT:-8889}"
WEBRTC_LOCAL_TCP_PORT="${WEBRTC_LOCAL_TCP_PORT:-8189}"
MEDIAMTX_BIND_HOST="${MEDIAMTX_BIND_HOST:-}"
BROWSER_PREVIEW_URI="${BROWSER_PREVIEW_URI_OVERRIDE:-http://127.0.0.1:${WEBRTC_PORT}/${STREAM_PATH}/}"
DEMO_VIDEO_FILE="${DEMO_VIDEO_FILE:-data/sample.mp4}"
USE_EXISTING_RTSP_SERVER="${USE_EXISTING_RTSP_SERVER:-0}"
STREAM_CHECK_TIMEOUT="${STREAM_CHECK_TIMEOUT:-20}"
SERVER_LOG="${SERVER_LOG:-/tmp/video_watch_assistant_mediamtx.log}"
MN_RUN_DIR="${MN_RUN_DIR:-}"
MN_POST_LAUNCH_STATE_FILE="${MN_POST_LAUNCH_STATE_FILE:-}"
if [[ -z "$MN_POST_LAUNCH_STATE_FILE" && -n "$MN_RUN_DIR" ]]; then
  MN_POST_LAUNCH_STATE_FILE="${MN_RUN_DIR}/post_launch_state.json"
fi
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
MN_PRE_LAUNCH_READY_FILE="${MN_PRE_LAUNCH_READY_FILE:-}"
OPENSHELL_STREAM_HOST="${OPENSHELL_STREAM_HOST:-}"

usage() {
  cat <<EOF
Start the host-side stream mapper for Video Watch Assistant.

Stable mapped RTSP endpoint:
  ${STREAM_URI}

The DockerWorker detector always consumes the stable mapped endpoint. This script
runs outside the worker container and feeds that endpoint from the demo video in
DEMO_VIDEO_FILE.

Environment overrides:
  DEMO_VIDEO_FILE Demo file to loop into the local RTSP endpoint.
  STREAM_URI      Local RTSP publish URI. Default: ${STREAM_URI}
  STREAM_PATH     MediaMTX path name. Default: ${STREAM_PATH}
  WEBRTC_PORT     Local MediaMTX browser preview port. Default: ${WEBRTC_PORT}
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required. Install it with: brew install ffmpeg" >&2
  exit 1
fi

cleanup_stale_mapper_on_start() {
  if [[ "$USE_EXISTING_RTSP_SERVER" == "1" ]]; then
    return 0
  fi
  local cleanup_script
  cleanup_script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/post-launch.sh"
  if [[ ! -f "$cleanup_script" ]]; then
    return 0
  fi
  echo "Checking for stale Video Watch Assistant mapper processes on ${RTSP_PORT}/${WEBRTC_PORT}."
  MN_POST_LAUNCH_REASON="pre_launch_preflight" \
    RTSP_PORT="$RTSP_PORT" \
    WEBRTC_PORT="$WEBRTC_PORT" \
    WEBRTC_LOCAL_TCP_PORT="$WEBRTC_LOCAL_TCP_PORT" \
    bash "$cleanup_script" || true
  cleanup_stale_pre_launch_hooks
}

is_local_port_open() {
  local port="$1"
  nc -z 127.0.0.1 "$port" >/dev/null 2>&1
}

current_process_group_id() {
  ps -p "$$" -o pgid= 2>/dev/null | tr -d '[:space:]' || true
}

process_group_exists() {
  local pgid="$1"
  [[ "$pgid" =~ ^[0-9]+$ ]] || return 1
  kill -0 -- "-$pgid" >/dev/null 2>&1
}

terminate_stale_process_group() {
  local pgid="$1"
  [[ "$pgid" =~ ^[0-9]+$ ]] || return 0
  [[ "$pgid" != "1" ]] || return 0
  if ! process_group_exists "$pgid"; then
    return 0
  fi
  echo "Stopping stale Video Watch Assistant pre-launch process group ${pgid}."
  kill -TERM -- "-$pgid" >/dev/null 2>&1 || true
  for _ in {1..30}; do
    if ! process_group_exists "$pgid"; then
      return 0
    fi
    sleep 0.1
  done
  kill -KILL -- "-$pgid" >/dev/null 2>&1 || true
}

cleanup_stale_pre_launch_hooks() {
  if ! command -v ps >/dev/null 2>&1; then
    return 0
  fi
  local script_path current_pgid
  script_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  current_pgid="$(current_process_group_id)"
  ps -axo pid=,pgid=,command= 2>/dev/null | while read -r pid pgid command; do
    if [[ -z "${pid:-}" || -z "${pgid:-}" || -z "${command:-}" ]]; then
      continue
    fi
    if [[ "$pid" == "$$" || "$pgid" == "$current_pgid" ]]; then
      continue
    fi
    case "$command" in
      *"$script_path"*)
        terminate_stale_process_group "$pgid"
        ;;
    esac
  done
}

is_port_open() {
  is_local_port_open "$RTSP_PORT"
}

refresh_stream_uri() {
  if [[ -z "$STREAM_URI_OVERRIDE" ]]; then
    STREAM_URI="rtsp://127.0.0.1:${RTSP_PORT}/${STREAM_PATH}"
  fi
}

refresh_browser_preview_uri() {
  if [[ -z "$BROWSER_PREVIEW_URI_OVERRIDE" ]]; then
    BROWSER_PREVIEW_URI="http://127.0.0.1:${WEBRTC_PORT}/${STREAM_PATH}/"
  fi
}

choose_available_port() {
  local variable_name="$1"
  local start_port="$2"
  local label="$3"
  local candidate
  for offset in {0..100}; do
    candidate=$((start_port + offset))
    if ! is_local_port_open "$candidate"; then
      printf -v "$variable_name" '%s' "$candidate"
      return 0
    fi
  done
  echo "No available ${label} port found starting at ${start_port}." >&2
  exit 1
}

detect_host_stream_host() {
  if [[ -n "$OPENSHELL_STREAM_HOST" ]]; then
    printf '%s\n' "$OPENSHELL_STREAM_HOST"
    return 0
  fi

  if command -v ipconfig >/dev/null 2>&1; then
    local iface ip
    for iface in en0 en1 bridge100; do
      ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
      if [[ -n "$ip" ]]; then
        printf '%s\n' "$ip"
        return 0
      fi
    done
  fi

  if command -v hostname >/dev/null 2>&1; then
    local ip
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    if [[ -n "$ip" ]]; then
      printf '%s\n' "$ip"
      return 0
    fi
  fi

  printf '127.0.0.1\n'
}

sandbox_stream_uri() {
  local host
  host="$(detect_host_stream_host)"
  printf 'rtsp://%s:%s/%s\n' "$host" "$RTSP_PORT" "$STREAM_PATH"
}

choose_available_rtsp_port() {
  local start_port="$RTSP_PORT"
  choose_available_port RTSP_PORT "$start_port" "local RTSP"
  refresh_stream_uri
}

choose_available_webrtc_ports() {
  local previous_port previous_tcp_port
  previous_port="$WEBRTC_PORT"
  previous_tcp_port="$WEBRTC_LOCAL_TCP_PORT"
  choose_available_port WEBRTC_PORT "$WEBRTC_PORT" "MediaMTX browser preview"
  choose_available_port WEBRTC_LOCAL_TCP_PORT "$WEBRTC_LOCAL_TCP_PORT" "MediaMTX WebRTC TCP"
  refresh_browser_preview_uri
  if [[ "$previous_port" != "$WEBRTC_PORT" ]]; then
    echo "Port ${previous_port} is already in use; selected browser preview port ${WEBRTC_PORT}."
  fi
  if [[ "$previous_tcp_port" != "$WEBRTC_LOCAL_TCP_PORT" ]]; then
    echo "Port ${previous_tcp_port} is already in use; selected MediaMTX WebRTC TCP port ${WEBRTC_LOCAL_TCP_PORT}."
  fi
}

mediamtx_address() {
  local port="$1"
  if [[ -n "$MEDIAMTX_BIND_HOST" ]]; then
    printf '%s:%s\n' "$MEDIAMTX_BIND_HOST" "$port"
  else
    printf ':%s\n' "$port"
  fi
}

server_pid=""
publisher_pid=""
config_dir=""

json_escape() {
  if command -v python3 >/dev/null 2>&1; then
    JSON_VALUE="$1" python3 - <<'PY'
import json
import os
print(json.dumps(os.environ.get("JSON_VALUE", "")))
PY
  else
    printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  fi
}

write_post_launch_state() {
  if [[ -z "$MN_POST_LAUNCH_STATE_FILE" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$MN_POST_LAUNCH_STATE_FILE")"
  cat >"$MN_POST_LAUNCH_STATE_FILE" <<EOF
{
  "schema": "otterdesk.video_watch.post_launch_state.v1",
  "run_id": $(json_escape "${MN_RUN_ID:-}"),
  "server_pid": $(json_escape "$server_pid"),
  "publisher_pid": $(json_escape "$publisher_pid"),
  "rtsp_port": $(json_escape "$RTSP_PORT"),
  "webrtc_port": $(json_escape "$WEBRTC_PORT"),
  "webrtc_local_tcp_port": $(json_escape "$WEBRTC_LOCAL_TCP_PORT"),
  "mediamtx_bind_host": $(json_escape "$MEDIAMTX_BIND_HOST"),
  "stream_path": $(json_escape "$STREAM_PATH"),
  "stream_uri": $(json_escape "$STREAM_URI"),
  "browser_preview_uri": $(json_escape "$BROWSER_PREVIEW_URI"),
  "server_log": $(json_escape "$SERVER_LOG"),
  "config_dir": $(json_escape "$config_dir"),
  "updated_at": $(json_escape "$(date -u +"%Y-%m-%dT%H:%M:%SZ")")
}
EOF
}

cleanup() {
  if [[ -n "$publisher_pid" ]]; then
    kill "$publisher_pid" >/dev/null 2>&1 || true
    wait "$publisher_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$config_dir" && -d "$config_dir" ]]; then
    rm -rf "$config_dir"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_rtsp_server() {
  local server_cmd=""
  if command -v mediamtx >/dev/null 2>&1; then
    server_cmd="mediamtx"
  elif command -v rtsp-simple-server >/dev/null 2>&1; then
    server_cmd="rtsp-simple-server"
  else
    echo "No RTSP server is listening on ${RTSP_PORT}, and mediamtx/rtsp-simple-server was not found." >&2
    echo "Install one with: brew install mediamtx" >&2
    exit 1
  fi

  choose_available_webrtc_ports

  config_dir="$(mktemp -d /tmp/video_watch_assistant_mediamtx.XXXXXX)"
  local config_path="${config_dir}/mediamtx.yml"
  cat >"$config_path" <<EOF
logLevel: info
rtspTransports: [tcp]
rtspAddress: $(mediamtx_address "$RTSP_PORT")
rtmp: false
hls: false
webrtc: true
webrtcAddress: $(mediamtx_address "$WEBRTC_PORT")
webrtcLocalUDPAddress: ''
webrtcLocalTCPAddress: $(mediamtx_address "$WEBRTC_LOCAL_TCP_PORT")
srt: false
paths:
  ${STREAM_PATH}:
    source: publisher
EOF

  echo "Starting ${server_cmd} on ${STREAM_URI}"
  echo "Browser preview will be available at ${BROWSER_PREVIEW_URI}"
  "$server_cmd" "$config_path" >"$SERVER_LOG" 2>&1 &
  server_pid="$!"
  write_post_launch_state

  for _ in {1..50}; do
    if is_port_open; then
      return 0
    fi
    sleep 0.1
  done

  echo "Timed out waiting for ${server_cmd} to listen on ${RTSP_PORT}." >&2
  echo "Server log: ${SERVER_LOG}" >&2
  exit 1
}

cleanup_stale_mapper_on_start

if is_port_open; then
  if [[ "$USE_EXISTING_RTSP_SERVER" != "1" ]]; then
    previous_port="$RTSP_PORT"
    choose_available_rtsp_port
    echo "Port ${previous_port} is already in use; selected RTSP port ${RTSP_PORT}."
    start_rtsp_server
  else
    echo "Using existing RTSP server on 127.0.0.1:${RTSP_PORT}"
  fi
else
  start_rtsp_server
fi

rtsp_stream_available() {
  local uri="${1:-$STREAM_URI}"
  ffprobe -v error -rtsp_transport tcp -rw_timeout 3000000 -show_entries stream=codec_type -of csv=p=0 "$uri" 2>/dev/null | grep -q "video"
}

wait_for_rtsp_stream() {
  local waited=0
  while (( waited < STREAM_CHECK_TIMEOUT )); do
    if rtsp_stream_available "$STREAM_URI"; then
      echo "RTSP stream is live at ${STREAM_URI}"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

demo_video_path() {
  local configured="$DEMO_VIDEO_FILE"
  if [[ "$configured" = /* ]]; then
    printf '%s\n' "$configured"
  else
    printf '%s\n' "$(pwd)/$configured"
  fi
}

mark_pre_launch_ready() {
  if [[ -z "$MN_PRE_LAUNCH_READY_FILE" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$MN_PRE_LAUNCH_READY_FILE")"
  local worker_stream_uri host_stream_host
  worker_stream_uri="$(sandbox_stream_uri)"
  host_stream_host="${worker_stream_uri#rtsp://}"
  host_stream_host="${host_stream_host%%:*}"
  cat >"$MN_PRE_LAUNCH_READY_FILE" <<EOF
{
  "status": "ready",
  "env": {
    "RTSP_PORT": "${RTSP_PORT}",
    "WEBRTC_PORT": "${WEBRTC_PORT}",
    "WEBRTC_LOCAL_TCP_PORT": "${WEBRTC_LOCAL_TCP_PORT}",
    "STREAM_PATH": "${STREAM_PATH}",
    "STREAM_URI": "${STREAM_URI}",
    "BROWSER_PREVIEW_URI": "${BROWSER_PREVIEW_URI}",
    "VIDEO_SOURCE_URI": "${worker_stream_uri}",
    "MN_HOST_STREAM_FALLBACK_HOSTS": "${host_stream_host},host.openshell.internal,host.docker.internal,192.168.65.254"
  },
  "config": {
    "video_source": {
      "uri": "${STREAM_URI}"
    },
    "web_ui": {
      "dashboard": {
        "default_video_source": "${STREAM_URI}",
        "browser_video_source": "${BROWSER_PREVIEW_URI}",
        "browser_publish_source": "disabled",
        "video_preview_bridge": {
          "enabled": false,
          "auto_start": false,
          "script": "scripts/pre-launch.sh",
          "stream_path": "${STREAM_PATH}",
          "rtsp_port": ${RTSP_PORT},
          "browser_video_source": "${BROWSER_PREVIEW_URI}",
          "cleanup_script": "scripts/post-launch.sh",
          "post_launch_state_file": "${MN_POST_LAUNCH_STATE_FILE}"
        }
      },
      "output": {
        "browser_video_source": "${BROWSER_PREVIEW_URI}",
        "browser_publish_source": "disabled"
      }
    }
  }
}
EOF
}

start_demo_publisher() {
  local video_file
  video_file="$(demo_video_path)"
  if [[ ! -f "$video_file" ]]; then
    echo "Demo video file not found: ${video_file}" >&2
    exit 1
  fi
  echo "Mapping demo video to ${STREAM_URI}"
  echo "Demo source: ${video_file}"
  ffmpeg \
    -hide_banner \
    -loglevel info \
    -nostdin \
    -stream_loop -1 \
    -re \
    -i "$video_file" \
    -an \
    -c:v libx264 \
    -preset veryfast \
    -tune zerolatency \
    -pix_fmt yuv420p \
    -b:v "$VIDEO_BITRATE" \
    -f rtsp \
    -rtsp_transport tcp \
    "$STREAM_URI" &
  publisher_pid="$!"
  write_post_launch_state
}

start_selected_publisher() {
  start_demo_publisher
}

echo "Keep this script running while the blueprint is active. Press Ctrl-C to stop."
echo "DockerWorker detector source: ${STREAM_URI}"
echo "Browser preview: ${BROWSER_PREVIEW_URI}"

while true; do
  start_selected_publisher
  if ! wait_for_rtsp_stream; then
    echo "Timed out waiting for mapper to publish ${STREAM_URI}." >&2
    echo "Server log: ${SERVER_LOG}" >&2
  else
    mark_pre_launch_ready
  fi

  wait "$publisher_pid" || true
  echo "Stream mapper stopped; restarting in 2s." >&2
  sleep 2
done
