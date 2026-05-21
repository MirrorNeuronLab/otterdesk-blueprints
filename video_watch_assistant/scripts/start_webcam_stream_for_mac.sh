#!/usr/bin/env bash
set -euo pipefail

RTSP_PORT="${RTSP_PORT:-8554}"
STREAM_PATH="${STREAM_PATH:-video-watch}"
STREAM_URI="${STREAM_URI:-rtsp://127.0.0.1:${RTSP_PORT}/${STREAM_PATH}}"
SOURCE_URI="${SOURCE_URI:-rtsp://9627b0bf2a7b.entrypoint.cloud.wowza.com:1935/app-p5260J38/66abe4b9_stream1}"
PUBLISH_MODE="${PUBLISH_MODE:-rtsp}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
USE_EXISTING_RTSP_SERVER="${USE_EXISTING_RTSP_SERVER:-0}"
CAMERA_DEVICE="${CAMERA_DEVICE:-0}"
CAMERA_AUDIO_DEVICE="${CAMERA_AUDIO_DEVICE:-none}"
CAMERA_PIXEL_FORMAT="${CAMERA_PIXEL_FORMAT:-uyvy422}"
VIDEO_SIZE="${VIDEO_SIZE:-1280x720}"
FRAMERATE="${FRAMERATE:-30}"
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
STREAM_CHECK_TIMEOUT="${STREAM_CHECK_TIMEOUT:-20}"
SERVER_LOG="${SERVER_LOG:-/tmp/video_watch_assistant_mediamtx.log}"
BROWSER_PREVIEW_URI="${BROWSER_PREVIEW_URI:-http://127.0.0.1:8889/${STREAM_PATH}/}"
BROWSER_PUBLISH_QUERY="${BROWSER_PUBLISH_QUERY:-video-codec=h264%2F90000&audio-device=none&video-width=1280&video-height=720&video-framerate=30}"
BROWSER_PUBLISH_URI="${BROWSER_PUBLISH_URI:-http://127.0.0.1:8889/${STREAM_PATH}/publish?${BROWSER_PUBLISH_QUERY}}"
RTSP_REPUBLISH_CODEC="${RTSP_REPUBLISH_CODEC:-copy}"

usage() {
  cat <<EOF
Start a browser-playable local preview bridge for Video Watch Assistant.

Default preview stream:
  ${STREAM_URI}

This script is only for the local browser preview. The OpenShell worker reads
SOURCE_URI directly, so no OpenShell network bridge or frame bridge is started.

Requirements:
  - network access to SOURCE_URI in rtsp mode
  - ffmpeg
  - mediamtx or rtsp-simple-server, unless another RTSP server is already listening on ${RTSP_PORT}

Usage:
  $(basename "$0") [--list-devices]

Environment overrides:
  SOURCE_URI      Upstream RTSP source to bridge in rtsp mode. Default: ${SOURCE_URI}
  STREAM_URI      Local RTSP publish URI for MediaMTX/browser preview. Default: ${STREAM_URI}
  STREAM_PATH     MediaMTX path name. Default: ${STREAM_PATH}
  PUBLISH_MODE    rtsp, browser, or ffmpeg. Default: ${PUBLISH_MODE}
  OPEN_BROWSER    Open the browser preview in rtsp mode, or publisher page in browser mode. Default: ${OPEN_BROWSER}
  USE_EXISTING_RTSP_SERVER
                 Reuse an RTSP server already listening on RTSP_PORT. Default: ${USE_EXISTING_RTSP_SERVER}
  RTSP_REPUBLISH_CODEC
                 ffmpeg video codec for rtsp mode. Use copy for the Wowza H.264 stream,
                 or libx264 to transcode. Default: ${RTSP_REPUBLISH_CODEC}
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
rtspAddress: :${RTSP_PORT}
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
  if ! command -v ffprobe >/dev/null 2>&1; then
    return 1
  fi
  ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_type -of csv=p=0 "$uri" >/dev/null 2>&1
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

open_browser_publisher() {
  if [[ "$OPEN_BROWSER" != "1" ]]; then
    return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "$BROWSER_PUBLISH_URI" >/dev/null 2>&1 || true
  fi
}

open_browser_preview() {
  if [[ "$OPEN_BROWSER" != "1" ]]; then
    return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "$BROWSER_PREVIEW_URI" >/dev/null 2>&1 || true
  fi
}

start_rtsp_republisher() {
  echo "Republishing upstream RTSP source to ${STREAM_URI}"
  echo "Upstream source: ${SOURCE_URI}"
  local codec_args=(-c:v "$RTSP_REPUBLISH_CODEC")
  if [[ "$RTSP_REPUBLISH_CODEC" == "copy" ]]; then
    codec_args=(-c:v copy)
  fi

  ffmpeg \
    -hide_banner \
    -loglevel info \
    -nostdin \
    -rtsp_transport tcp \
    -i "$SOURCE_URI" \
    -an \
    "${codec_args[@]}" \
    -f rtsp \
    -rtsp_transport tcp \
    "$STREAM_URI" &
  publisher_pid="$!"
}

start_ffmpeg_camera_publisher() {
  local input="${CAMERA_DEVICE}"
  if [[ -n "$CAMERA_AUDIO_DEVICE" ]]; then
    input="${CAMERA_DEVICE}:${CAMERA_AUDIO_DEVICE}"
  fi
  local input_args=(
    -hide_banner
    -loglevel info
    -nostdin
    -f avfoundation
    -framerate "$FRAMERATE"
  )
  if [[ -n "$CAMERA_PIXEL_FORMAT" && "$CAMERA_PIXEL_FORMAT" != "auto" ]]; then
    input_args+=(-pixel_format "$CAMERA_PIXEL_FORMAT")
  fi
  if [[ -n "$VIDEO_SIZE" && "$VIDEO_SIZE" != "auto" ]]; then
    input_args+=(-video_size "$VIDEO_SIZE")
  fi

  echo "Publishing Mac camera '${input}' to ${STREAM_URI} with ffmpeg"
  ffmpeg \
    "${input_args[@]}" \
    -i "$input" \
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

echo "Keep this script running while the blueprint is active. Press Ctrl-C to stop."
echo "Worker video source: ${SOURCE_URI}"
echo "Browser preview: ${BROWSER_PREVIEW_URI}"

case "$PUBLISH_MODE" in
  rtsp)
    preview_opened=0
    while true; do
      start_rtsp_republisher
      if ! wait_for_rtsp_stream; then
        echo "Timed out waiting for upstream RTSP republish to make ${STREAM_URI} available." >&2
        echo "Check SOURCE_URI with: ffplay -rtsp_transport tcp \"${SOURCE_URI}\"" >&2
        echo "Server log: ${SERVER_LOG}" >&2
      elif [[ "$preview_opened" != "1" ]]; then
        open_browser_preview
        preview_opened=1
      fi

      wait "$publisher_pid" || true
      echo "RTSP republisher stopped; restarting in 2s." >&2
      sleep 2
    done
    ;;
  browser)
    echo "Open the browser webcam publisher, allow camera access, and click Publish."
    open_browser_publisher
    echo "Waiting for the browser publisher to make ${STREAM_URI} available."
    while true; do
      if rtsp_stream_available "$STREAM_URI"; then
        echo "RTSP stream is live at ${STREAM_URI}"
        break
      fi
      sleep 2
    done
    while true; do
      sleep 1
    done
    ;;
  ffmpeg)
    start_ffmpeg_camera_publisher
    if ! wait_for_rtsp_stream; then
      echo "Timed out waiting for ffmpeg camera capture to make ${STREAM_URI} available." >&2
      echo "Server log: ${SERVER_LOG}" >&2
    fi
    wait "$publisher_pid"
    ;;
  *)
    echo "Unsupported PUBLISH_MODE '${PUBLISH_MODE}'. Use rtsp, browser, or ffmpeg." >&2
    exit 1
    ;;
esac
