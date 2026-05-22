#!/usr/bin/env bash
set -euo pipefail

RTSP_PORT="${RTSP_PORT:-8554}"
STREAM_PATH="${STREAM_PATH:-video-watch}"
STREAM_URI="${STREAM_URI:-rtsp://127.0.0.1:${RTSP_PORT}/${STREAM_PATH}}"
DEMO_VIDEO_FILE="${DEMO_VIDEO_FILE:-data/sample.mp4}"
USE_EXISTING_RTSP_SERVER="${USE_EXISTING_RTSP_SERVER:-0}"
STREAM_CHECK_TIMEOUT="${STREAM_CHECK_TIMEOUT:-20}"
SERVER_LOG="${SERVER_LOG:-/tmp/video_watch_assistant_mediamtx.log}"
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
MN_PRE_LAUNCH_READY_FILE="${MN_PRE_LAUNCH_READY_FILE:-}"

usage() {
  cat <<EOF
Start the host-side stream mapper for Video Watch Assistant.

Stable mapped RTSP endpoint:
  ${STREAM_URI}

The OpenShell worker always consumes the stable mapped endpoint. This script
runs outside OpenShell and feeds that endpoint from the demo video in
DEMO_VIDEO_FILE.

Environment overrides:
  DEMO_VIDEO_FILE Demo file to loop into the local RTSP endpoint.
  STREAM_URI      Local RTSP publish URI. Default: ${STREAM_URI}
  STREAM_PATH     MediaMTX path name. Default: ${STREAM_PATH}
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

is_port_open() {
  nc -z 127.0.0.1 "$RTSP_PORT" >/dev/null 2>&1
}

server_pid=""
publisher_pid=""
config_dir=""

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

  config_dir="$(mktemp -d /tmp/video_watch_assistant_mediamtx.XXXXXX)"
  local config_path="${config_dir}/mediamtx.yml"
  cat >"$config_path" <<EOF
logLevel: info
rtspTransports: [tcp]
rtspAddress: :${RTSP_PORT}
rtmp: false
hls: false
webrtc: true
webrtcAddress: :8889
webrtcLocalUDPAddress: ''
webrtcLocalTCPAddress: :8189
srt: false
paths:
  ${STREAM_PATH}:
    source: publisher
EOF

  echo "Starting ${server_cmd} on ${STREAM_URI}"
  "$server_cmd" "$config_path" >"$SERVER_LOG" 2>&1 &
  server_pid="$!"

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

if is_port_open; then
  if [[ "$USE_EXISTING_RTSP_SERVER" != "1" ]]; then
    echo "Port ${RTSP_PORT} is already in use. Stop the existing RTSP server or set USE_EXISTING_RTSP_SERVER=1." >&2
    exit 1
  fi
  echo "Using existing RTSP server on 127.0.0.1:${RTSP_PORT}"
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
  printf 'ready\n' >"$MN_PRE_LAUNCH_READY_FILE"
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
}

start_selected_publisher() {
  start_demo_publisher
}

echo "Keep this script running while the blueprint is active. Press Ctrl-C to stop."
echo "OpenShell worker source: ${STREAM_URI}"

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
