#!/usr/bin/env bash
set -euo pipefail

RTSP_PORT="${RTSP_PORT:-8554}"
STREAM_PATH="${STREAM_PATH:-local-camera}"
STREAM_URI="${STREAM_URI:-rtsp://127.0.0.1:${RTSP_PORT}/${STREAM_PATH}}"
PUBLISH_MODE="${PUBLISH_MODE:-browser}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
USE_EXISTING_RTSP_SERVER="${USE_EXISTING_RTSP_SERVER:-0}"
CAMERA_DEVICE="${CAMERA_DEVICE:-0}"
CAMERA_AUDIO_DEVICE="${CAMERA_AUDIO_DEVICE:-none}"
CAMERA_PIXEL_FORMAT="${CAMERA_PIXEL_FORMAT:-uyvy422}"
VIDEO_FILE="${VIDEO_FILE:-}"
VIDEO_SIZE="${VIDEO_SIZE:-1280x720}"
FRAMERATE="${FRAMERATE:-30}"
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
STREAM_CHECK_TIMEOUT="${STREAM_CHECK_TIMEOUT:-20}"
SERVER_LOG="${SERVER_LOG:-/tmp/business_facility_safety_video_guardian_mediamtx.log}"
BROWSER_PREVIEW_URI="${BROWSER_PREVIEW_URI:-http://127.0.0.1:8889/${STREAM_PATH}/}"
BROWSER_PUBLISH_QUERY="${BROWSER_PUBLISH_QUERY:-video-codec=h264%2F90000&audio-device=none&video-width=1280&video-height=720&video-framerate=30}"
BROWSER_PUBLISH_URI="${BROWSER_PUBLISH_URI:-http://127.0.0.1:8889/${STREAM_PATH}/publish?${BROWSER_PUBLISH_QUERY}}"

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
  STREAM_PATH     MediaMTX path name. Default: ${STREAM_PATH}
  PUBLISH_MODE    browser, ffmpeg, or file. Default: ${PUBLISH_MODE}
  OPEN_BROWSER    Open the browser publisher page in browser mode. Default: ${OPEN_BROWSER}
  USE_EXISTING_RTSP_SERVER
                 Reuse an RTSP server already listening on RTSP_PORT. Default: ${USE_EXISTING_RTSP_SERVER}
  CAMERA_DEVICE   avfoundation video device index or name. Default: ${CAMERA_DEVICE}
  CAMERA_AUDIO_DEVICE
                 avfoundation audio device index/name, or none. Default: ${CAMERA_AUDIO_DEVICE}
  CAMERA_PIXEL_FORMAT
                 avfoundation input pixel format. Default: ${CAMERA_PIXEL_FORMAT}
  VIDEO_FILE      Optional video file to loop and publish instead of using the Mac camera.
  VIDEO_SIZE      Capture size. Default: ${VIDEO_SIZE}
  FRAMERATE       Capture framerate. Default: ${FRAMERATE}
  VIDEO_BITRATE   H.264 bitrate. Default: ${VIDEO_BITRATE}
  BROWSER_PUBLISH_QUERY
                 MediaMTX browser publisher query. Default requests H.264 video and no audio.
  BROWSER_PUBLISH_URI
                 Browser webcam publisher URL. Default: ${BROWSER_PUBLISH_URI}

Examples:
  scripts/start_demo_camera_stream_for_mac.sh
  OPEN_BROWSER=0 scripts/start_demo_camera_stream_for_mac.sh
  VIDEO_FILE=payloads/person_detector/samples/door-demo.mp4 scripts/start_demo_camera_stream_for_mac.sh
  PUBLISH_MODE=ffmpeg CAMERA_DEVICE="FaceTime HD Camera" scripts/start_demo_camera_stream_for_mac.sh
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
publisher_pid=""
config_path=""
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

  config_dir="$(mktemp -d /tmp/business_facility_safety_video_guardian_mediamtx.XXXXXX)"
  config_path="${config_dir}/mediamtx.yml"
  cat >"$config_path" <<EOF
logLevel: info
rtspAddress: :${RTSP_PORT}
paths:
  ${STREAM_PATH}:
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
  if [[ "$USE_EXISTING_RTSP_SERVER" != "1" ]]; then
    echo "Port ${RTSP_PORT} is already in use. Stop the existing RTSP server or set USE_EXISTING_RTSP_SERVER=1." >&2
    exit 1
  fi
  echo "Using existing RTSP server on 127.0.0.1:${RTSP_PORT}"
else
  start_rtsp_server
fi

if [[ -n "$VIDEO_FILE" ]]; then
  PUBLISH_MODE="file"
  if [[ ! -f "$VIDEO_FILE" ]]; then
    echo "VIDEO_FILE does not exist: ${VIDEO_FILE}" >&2
    exit 1
  fi
fi

rtsp_stream_available() {
  if ! command -v ffprobe >/dev/null 2>&1; then
    return 1
  fi
  ffprobe \
    -v error \
    -rtsp_transport tcp \
    -show_entries stream=codec_type \
    -of csv=p=0 \
    "$STREAM_URI" >/dev/null 2>&1
}

wait_for_rtsp_stream() {
  local waited=0
  while (( waited < STREAM_CHECK_TIMEOUT )); do
    if rtsp_stream_available; then
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

start_file_publisher() {
  echo "Publishing video file '${VIDEO_FILE}' to ${STREAM_URI}"
  ffmpeg \
    -hide_banner \
    -loglevel info \
    -nostdin \
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
echo "Browser preview: ${BROWSER_PREVIEW_URI}"
echo "Browser webcam publisher: ${BROWSER_PUBLISH_URI}"

case "$PUBLISH_MODE" in
  browser)
    echo "Open the browser webcam publisher, allow camera access, and click Publish."
    open_browser_publisher
    echo "Waiting for the browser publisher to make ${STREAM_URI} available."
    while true; do
      if rtsp_stream_available; then
        echo "RTSP stream is live at ${STREAM_URI}"
        break
      fi
      sleep 2
    done
    while true; do
      sleep 1
    done
    ;;
  file)
    start_file_publisher
    if ! wait_for_rtsp_stream; then
      echo "Timed out waiting for the file publisher to make ${STREAM_URI} available." >&2
      echo "Server log: ${SERVER_LOG}" >&2
    fi
    wait "$publisher_pid"
    ;;
  ffmpeg)
    start_ffmpeg_camera_publisher
    if ! wait_for_rtsp_stream; then
      echo "Timed out waiting for ffmpeg camera capture to make ${STREAM_URI} available." >&2
      echo "If the camera light is on but no stream appears, use the default browser publisher mode instead." >&2
      echo "Server log: ${SERVER_LOG}" >&2
    fi
    wait "$publisher_pid"
    ;;
  *)
    echo "Unsupported PUBLISH_MODE '${PUBLISH_MODE}'. Use browser, ffmpeg, or file." >&2
    exit 1
    ;;
esac
