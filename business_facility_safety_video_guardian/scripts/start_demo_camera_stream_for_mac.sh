#!/usr/bin/env bash
set -euo pipefail

STREAM_URI="${STREAM_URI:-rtsp://127.0.0.1:8554/local-camera}"
RTSP_PORT="${RTSP_PORT:-8554}"
CAMERA_DEVICE="${CAMERA_DEVICE:-0}"
VIDEO_FILE="${VIDEO_FILE:-}"
VIDEO_SIZE="${VIDEO_SIZE:-1280x720}"
FRAMERATE="${FRAMERATE:-30}"
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
SERVER_LOG="${SERVER_LOG:-/tmp/business_facility_safety_video_guardian_mediamtx.log}"

usage() {
  cat <<EOF
Start a local RTSP stream from this Mac's camera for Facility Safety Video Guardian.

Default stream:
  ${STREAM_URI}

Requirements:
  - macOS camera permission for the terminal app running this script
  - ffmpeg with avfoundation support
  - mediamtx or rtsp-simple-server, unless another RTSP server is already listening on ${RTSP_PORT}

Usage:
  $(basename "$0") [--list-devices]

Environment overrides:
  STREAM_URI      RTSP publish URI. Default: ${STREAM_URI}
  CAMERA_DEVICE   avfoundation video device index or name. Default: ${CAMERA_DEVICE}
  VIDEO_FILE      Optional video file to loop and publish instead of using the Mac camera.
  VIDEO_SIZE      Capture size. Default: ${VIDEO_SIZE}
  FRAMERATE       Capture framerate. Default: ${FRAMERATE}
  VIDEO_BITRATE   H.264 bitrate. Default: ${VIDEO_BITRATE}

Examples:
  scripts/start_demo_camera_stream_for_mac.sh
  VIDEO_FILE=payloads/person_detector/samples/door-demo.mp4 scripts/start_demo_camera_stream_for_mac.sh
  CAMERA_DEVICE="FaceTime HD Camera" scripts/start_demo_camera_stream_for_mac.sh
  scripts/start_demo_camera_stream_for_mac.sh --list-devices
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

if [[ "${1:-}" == "--list-devices" ]]; then
  ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 || true
  exit 0
fi

is_port_open() {
  nc -z 127.0.0.1 "$RTSP_PORT" >/dev/null 2>&1
}

server_pid=""
config_path=""
config_dir=""

cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$config_dir" && -d "$config_dir" ]]; then
    rm -rf "$config_dir"
  fi
}
trap cleanup EXIT INT TERM

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

  config_dir="$(mktemp -d /tmp/business_facility_safety_video_guardian_mediamtx.XXXXXX)"
  config_path="${config_dir}/mediamtx.yml"
  cat >"$config_path" <<EOF
logLevel: info
rtspAddress: :${RTSP_PORT}
paths:
  local-camera:
    source: publisher
EOF

  echo "Starting ${server_cmd} on rtsp://127.0.0.1:${RTSP_PORT}/local-camera"
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
  echo "Using existing RTSP server on 127.0.0.1:${RTSP_PORT}"
else
  start_rtsp_server
fi

if [[ -n "$VIDEO_FILE" ]]; then
  if [[ ! -f "$VIDEO_FILE" ]]; then
    echo "VIDEO_FILE does not exist: ${VIDEO_FILE}" >&2
    exit 1
  fi
  echo "Publishing video file '${VIDEO_FILE}' to ${STREAM_URI}"
else
  echo "Publishing Mac camera '${CAMERA_DEVICE}' to ${STREAM_URI}"
fi
echo "Keep this script running while the blueprint is active. Press Ctrl-C to stop."

if [[ -n "$VIDEO_FILE" ]]; then
  ffmpeg \
    -hide_banner \
    -loglevel info \
    -re \
    -stream_loop -1 \
    -i "$VIDEO_FILE" \
    -an \
    -c:v libx264 \
    -preset veryfast \
    -tune zerolatency \
    -pix_fmt yuv420p \
    -b:v "$VIDEO_BITRATE" \
    -f rtsp \
    -rtsp_transport tcp \
    "$STREAM_URI"
else
  ffmpeg \
    -hide_banner \
    -loglevel info \
    -f avfoundation \
    -framerate "$FRAMERATE" \
    -video_size "$VIDEO_SIZE" \
    -i "${CAMERA_DEVICE}:none" \
    -an \
    -c:v libx264 \
    -preset veryfast \
    -tune zerolatency \
    -pix_fmt yuv420p \
    -b:v "$VIDEO_BITRATE" \
    -f rtsp \
    -rtsp_transport tcp \
    "$STREAM_URI"
fi
