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
VIDEO_SIZE="${VIDEO_SIZE:-1280x720}"
FRAMERATE="${FRAMERATE:-30}"
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
STREAM_CHECK_TIMEOUT="${STREAM_CHECK_TIMEOUT:-20}"
SERVER_LOG="${SERVER_LOG:-/tmp/business_facility_safety_video_guardian_mediamtx.log}"
BROWSER_PREVIEW_URI="${BROWSER_PREVIEW_URI:-http://127.0.0.1:8889/${STREAM_PATH}/}"
BROWSER_PUBLISH_QUERY="${BROWSER_PUBLISH_QUERY:-video-codec=h264%2F90000&audio-device=none&video-width=1280&video-height=720&video-framerate=30}"
BROWSER_PUBLISH_URI="${BROWSER_PUBLISH_URI:-http://127.0.0.1:8889/${STREAM_PATH}/publish?${BROWSER_PUBLISH_QUERY}}"
OPENSHELL_RTSP_TUNNEL="${OPENSHELL_RTSP_TUNNEL:-1}"
OPENSHELL_FRAME_BRIDGE="${OPENSHELL_FRAME_BRIDGE:-1}"
OPENSHELL_FRAME_BRIDGE_INTERVAL_SECONDS="${OPENSHELL_FRAME_BRIDGE_INTERVAL_SECONDS:-1}"
OPENSHELL_FRAME_GRAB_TIMEOUT_SECONDS="${OPENSHELL_FRAME_GRAB_TIMEOUT_SECONDS:-10}"
OPENSHELL_FRAME_BRIDGE_REMOTE_DIR="${OPENSHELL_FRAME_BRIDGE_REMOTE_DIR:-/sandbox/live}"
OPENSHELL_FRAME_BRIDGE_LOG="${OPENSHELL_FRAME_BRIDGE_LOG:-/tmp/business_facility_safety_video_guardian_openshell_frame_bridge.log}"
OPENSHELL_SANDBOX_NAME="${OPENSHELL_SANDBOX_NAME:-}"
OPENSHELL_SANDBOX_PATTERN="${OPENSHELL_SANDBOX_PATTERN:-mirror-neuron-job-bfsvgv}"
OPENSHELL_TUNNEL_LOG="${OPENSHELL_TUNNEL_LOG:-/tmp/business_facility_safety_video_guardian_openshell_rtsp_tunnel.log}"

usage() {
  cat <<EOF
Start a local RTSP stream from this Mac's webcam for Facility Safety Video Guardian.

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
  PUBLISH_MODE    browser or ffmpeg. Default: ${PUBLISH_MODE}
  OPEN_BROWSER    Open the browser publisher page in browser mode. Default: ${OPEN_BROWSER}
  USE_EXISTING_RTSP_SERVER
                 Reuse an RTSP server already listening on RTSP_PORT. Default: ${USE_EXISTING_RTSP_SERVER}
  CAMERA_DEVICE   avfoundation video device index or name. Default: ${CAMERA_DEVICE}
  CAMERA_AUDIO_DEVICE
                 avfoundation audio device index/name, or none. Default: ${CAMERA_AUDIO_DEVICE}
  CAMERA_PIXEL_FORMAT
                 avfoundation input pixel format. Default: ${CAMERA_PIXEL_FORMAT}
  VIDEO_SIZE      Capture size. Default: ${VIDEO_SIZE}
  FRAMERATE       Capture framerate. Default: ${FRAMERATE}
  VIDEO_BITRATE   H.264 bitrate. Default: ${VIDEO_BITRATE}
  BROWSER_PUBLISH_QUERY
                 MediaMTX browser publisher query. Default requests H.264 video and no audio.
  BROWSER_PUBLISH_URI
                 Browser webcam publisher URL. Default: ${BROWSER_PUBLISH_URI}
  OPENSHELL_RTSP_TUNNEL
                 Create a reverse SSH tunnel into the detector OpenShell sandbox so
                 sandbox-local rtsp://127.0.0.1:${RTSP_PORT}/${STREAM_PATH} reaches this Mac.
                 Default: ${OPENSHELL_RTSP_TUNNEL}
  OPENSHELL_FRAME_BRIDGE
                 Upload a rolling latest.jpg frame into the detector OpenShell sandbox.
                 Default: ${OPENSHELL_FRAME_BRIDGE}
  OPENSHELL_FRAME_GRAB_TIMEOUT_SECONDS
                 Kill one stalled frame grab after this many seconds so the bridge keeps retrying.
                 Default: ${OPENSHELL_FRAME_GRAB_TIMEOUT_SECONDS}
  OPENSHELL_FRAME_BRIDGE_REMOTE_DIR
                 Remote sandbox directory for latest.jpg. Default: ${OPENSHELL_FRAME_BRIDGE_REMOTE_DIR}
  OPENSHELL_SANDBOX_NAME
                 Optional exact detector sandbox name. If omitted, the script waits for the
                 newest Ready sandbox matching OPENSHELL_SANDBOX_PATTERN.
  OPENSHELL_SANDBOX_PATTERN
                 Sandbox name substring used when OPENSHELL_SANDBOX_NAME is omitted.
                 Default: ${OPENSHELL_SANDBOX_PATTERN}

Examples:
  scripts/start_webcam_stream_for_mac.sh
  OPEN_BROWSER=0 scripts/start_webcam_stream_for_mac.sh
  PUBLISH_MODE=ffmpeg CAMERA_DEVICE="FaceTime HD Camera" scripts/start_webcam_stream_for_mac.sh
  CAMERA_DEVICE="FaceTime HD Camera" scripts/start_webcam_stream_for_mac.sh
  scripts/start_webcam_stream_for_mac.sh --list-devices
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
tunnel_pid=""
frame_bridge_pid=""
config_path=""
config_dir=""
tunnel_config_path=""
tunnel_config_dir=""
frame_bridge_dir=""

cleanup() {
  if [[ -n "$frame_bridge_pid" ]]; then
    kill "$frame_bridge_pid" >/dev/null 2>&1 || true
    wait "$frame_bridge_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$tunnel_pid" ]]; then
    kill "$tunnel_pid" >/dev/null 2>&1 || true
    wait "$tunnel_pid" >/dev/null 2>&1 || true
  fi
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
  if [[ -n "$tunnel_config_dir" && -d "$tunnel_config_dir" ]]; then
    rm -rf "$tunnel_config_dir"
  fi
  if [[ -n "$frame_bridge_dir" && -d "$frame_bridge_dir" ]]; then
    rm -rf "$frame_bridge_dir"
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

if [[ "$PUBLISH_MODE" == "file" || -n "${VIDEO_FILE:-}" ]]; then
  echo "File-backed video publishing is disabled for this blueprint. Use browser or ffmpeg webcam mode." >&2
  exit 1
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

latest_ready_openshell_sandbox() {
  if [[ -n "$OPENSHELL_SANDBOX_NAME" ]]; then
    if openshell sandbox get "$OPENSHELL_SANDBOX_NAME" 2>/dev/null | grep -q "Phase: Ready"; then
      printf '%s\n' "$OPENSHELL_SANDBOX_NAME"
      return 0
    fi
    return 1
  fi

  openshell sandbox list 2>/dev/null \
    | awk -v pattern="$OPENSHELL_SANDBOX_PATTERN" '$1 ~ pattern && $0 ~ /Ready/ {name=$1} END {if (name) print name}'
}

start_openshell_rtsp_tunnel() {
  if [[ "$OPENSHELL_RTSP_TUNNEL" != "1" ]]; then
    return 0
  fi
  if ! command -v openshell >/dev/null 2>&1 || ! command -v ssh >/dev/null 2>&1; then
    echo "OpenShell RTSP tunnel skipped: openshell and ssh are required." >&2
    return 0
  fi

  tunnel_config_dir="$(mktemp -d /tmp/business_facility_safety_video_guardian_openshell_tunnel.XXXXXX)"
  tunnel_config_path="${tunnel_config_dir}/ssh_config"
  : >"$OPENSHELL_TUNNEL_LOG"

  (
    set +e
    current_sandbox=""
    while true; do
      sandbox_name="$(latest_ready_openshell_sandbox)"
      if [[ -z "$sandbox_name" ]]; then
        sleep 1
        continue
      fi

      if [[ "$sandbox_name" != "$current_sandbox" ]]; then
        echo "Opening OpenShell RTSP tunnel to ${sandbox_name}" >>"$OPENSHELL_TUNNEL_LOG"
        current_sandbox="$sandbox_name"
      fi

      if ! openshell sandbox ssh-config "$sandbox_name" >"$tunnel_config_path" 2>>"$OPENSHELL_TUNNEL_LOG"; then
        sleep 2
        continue
      fi

      ssh_host="openshell-${sandbox_name}"
      ssh \
        -F "$tunnel_config_path" \
        -N \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=10 \
        -o ServerAliveCountMax=2 \
        -R "127.0.0.1:${RTSP_PORT}:127.0.0.1:${RTSP_PORT}" \
        "$ssh_host" >>"$OPENSHELL_TUNNEL_LOG" 2>&1

      sleep 2
    done
  ) &
  tunnel_pid="$!"
  echo "OpenShell RTSP tunnel watcher started (log: ${OPENSHELL_TUNNEL_LOG})"
}

grab_latest_frame() {
  local frame_path="$1"
  ffmpeg \
    -hide_banner \
    -loglevel error \
    -nostdin \
    -rtsp_transport tcp \
    -i "$STREAM_URI" \
    -frames:v 1 \
    -q:v 4 \
    -y \
    "$frame_path" >>"$OPENSHELL_FRAME_BRIDGE_LOG" 2>&1 &

  local grab_pid="$!"
  local waited=0
  while kill -0 "$grab_pid" >/dev/null 2>&1; do
    if (( waited >= OPENSHELL_FRAME_GRAB_TIMEOUT_SECONDS )); then
      echo "Frame grab timed out after ${OPENSHELL_FRAME_GRAB_TIMEOUT_SECONDS}s; retrying." >>"$OPENSHELL_FRAME_BRIDGE_LOG"
      kill "$grab_pid" >/dev/null 2>&1 || true
      wait "$grab_pid" >/dev/null 2>&1 || true
      return 124
    fi
    sleep 1
    waited=$((waited + 1))
  done

  wait "$grab_pid"
}

start_openshell_frame_bridge() {
  if [[ "$OPENSHELL_FRAME_BRIDGE" != "1" ]]; then
    return 0
  fi
  if ! command -v openshell >/dev/null 2>&1; then
    echo "OpenShell frame bridge skipped: openshell is required." >&2
    return 0
  fi

  frame_bridge_dir="$(mktemp -d /tmp/business_facility_safety_video_guardian_frames.XXXXXX)"
  : >"$OPENSHELL_FRAME_BRIDGE_LOG"

  (
    set +e
    current_sandbox=""
    while true; do
      sandbox_name="$(latest_ready_openshell_sandbox)"
      if [[ -z "$sandbox_name" ]]; then
        sleep 1
        continue
      fi

      if [[ "$sandbox_name" != "$current_sandbox" ]]; then
        echo "Uploading live frames to ${sandbox_name}:${OPENSHELL_FRAME_BRIDGE_REMOTE_DIR}/latest.jpg" >>"$OPENSHELL_FRAME_BRIDGE_LOG"
        current_sandbox="$sandbox_name"
      fi

      frame_path="${frame_bridge_dir}/latest.jpg"
      grab_latest_frame "$frame_path"

      if [[ -s "$frame_path" ]]; then
        openshell sandbox upload "$sandbox_name" "$frame_bridge_dir" "$OPENSHELL_FRAME_BRIDGE_REMOTE_DIR" --no-git-ignore >>"$OPENSHELL_FRAME_BRIDGE_LOG" 2>&1
      fi

      sleep "$OPENSHELL_FRAME_BRIDGE_INTERVAL_SECONDS"
    done
  ) &
  frame_bridge_pid="$!"
  echo "OpenShell live frame bridge started (log: ${OPENSHELL_FRAME_BRIDGE_LOG})"
}

open_browser_publisher() {
  if [[ "$OPEN_BROWSER" != "1" ]]; then
    return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "$BROWSER_PUBLISH_URI" >/dev/null 2>&1 || true
  fi
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
start_openshell_rtsp_tunnel
start_openshell_frame_bridge

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
    echo "Unsupported PUBLISH_MODE '${PUBLISH_MODE}'. Use browser or ffmpeg." >&2
    exit 1
    ;;
esac
