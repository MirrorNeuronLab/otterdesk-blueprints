#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BLUEPRINT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

CONTAINER_NAME="${CCTV_SAMPLE_RTSP_CONTAINER:-cctv-sample-rtsp}"
MEDIAMTX_IMAGE="${CCTV_SAMPLE_RTSP_IMAGE:-bluenviron/mediamtx:latest}"
RTSP_PORT="${CCTV_SAMPLE_RTSP_PORT:-8554}"
RTSP_PATH="${CCTV_SAMPLE_RTSP_PATH:-cctv-sample}"
STATE_DIR="${CCTV_SAMPLE_RTSP_STATE_DIR:-${TMPDIR:-/tmp}/cctv-sample-rtsp-${USER:-user}}"
PID_FILE="${STATE_DIR}/ffmpeg.pid"
URL_FILE="${STATE_DIR}/publish.url"
FFMPEG_LOG="${STATE_DIR}/ffmpeg.log"

usage() {
  cat <<'EOF'
Usage:
  sample_rtsp.sh start [video-file]
  sample_rtsp.sh stop
  sample_rtsp.sh status

Starts a MediaMTX RTSP server and publishes a looping sample video with
FFmpeg. The default video is examples/sample_inputs/sample.mp4.

Optional environment variables:
  CCTV_SAMPLE_VIDEO              Default input video path
  CCTV_SAMPLE_RTSP_HOST          Host/IP printed for DockerWorker access
  CCTV_SAMPLE_RTSP_PORT          Host RTSP port (default: 8554)
  CCTV_SAMPLE_RTSP_PATH          RTSP stream path (default: cctv-sample)
  CCTV_SAMPLE_RTSP_CONTAINER     MediaMTX container name
  CCTV_SAMPLE_RTSP_IMAGE         MediaMTX image
  CCTV_SAMPLE_RTSP_STATE_DIR     PID and log directory
EOF
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

local_rtsp_url() {
  printf 'rtsp://127.0.0.1:%s/%s' "${RTSP_PORT}" "${RTSP_PATH}"
}

public_host() {
  if [[ -n "${CCTV_SAMPLE_RTSP_HOST:-}" ]]; then
    printf '%s' "${CCTV_SAMPLE_RTSP_HOST}"
    return
  fi

  local detected_host=""
  if command -v hostname >/dev/null 2>&1; then
    detected_host="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  printf '%s' "${detected_host:-127.0.0.1}"
}

public_rtsp_url() {
  printf 'rtsp://%s:%s/%s' "$(public_host)" "${RTSP_PORT}" "${RTSP_PATH}"
}

container_exists() {
  docker container inspect "${CONTAINER_NAME}" >/dev/null 2>&1
}

container_is_running() {
  [[ "$(docker container inspect --format '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null || true)" == "true" ]]
}

recorded_publisher_is_running() {
  local pid=""
  [[ -r "${PID_FILE}" ]] || return 1
  read -r pid <"${PID_FILE}" || return 1
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

stop_publisher() {
  local pid=""
  local recorded_url=""
  local command_line=""

  if [[ -r "${PID_FILE}" ]]; then
    read -r pid <"${PID_FILE}" || true
  fi
  if [[ -r "${URL_FILE}" ]]; then
    read -r recorded_url <"${URL_FILE}" || true
  fi

  if [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null; then
    command_line="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
    if [[ "${command_line}" == *ffmpeg* ]] &&
       [[ -n "${recorded_url}" ]] &&
       [[ "${command_line}" == *"${recorded_url}"* ]]; then
      kill "${pid}" 2>/dev/null || true
      for _ in {1..25}; do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 0.2
      done
      if kill -0 "${pid}" 2>/dev/null; then
        kill -KILL "${pid}" 2>/dev/null || true
      fi
      echo "Stopped FFmpeg publisher (PID ${pid})."
    else
      echo "Warning: PID ${pid} no longer matches this publisher; leaving it running." >&2
    fi
  fi

  rm -f -- "${PID_FILE}" "${URL_FILE}"
}

stop_server() {
  if container_exists; then
    docker rm -f "${CONTAINER_NAME}" >/dev/null
    echo "Stopped MediaMTX container ${CONTAINER_NAME}."
  fi
}

stop_all() {
  require_command docker
  stop_publisher
  stop_server
}

wait_for_rtsp_server() {
  for _ in {1..20}; do
    if (exec 3<>"/dev/tcp/127.0.0.1/${RTSP_PORT}") 2>/dev/null; then
      return 0
    fi
    container_is_running || return 1
    sleep 0.5
  done
  return 1
}

wait_for_stream() {
  local stream_url="$1"
  for _ in {1..30}; do
    if ffprobe \
      -v error \
      -rtsp_transport tcp \
      -show_entries stream=codec_name,width,height \
      -of default=noprint_wrappers=1 \
      "${stream_url}" >/dev/null 2>&1; then
      return 0
    fi
    recorded_publisher_is_running || return 1
    sleep 1
  done
  return 1
}

print_status() {
  require_command docker

  if container_is_running; then
    echo "MediaMTX: running (${CONTAINER_NAME})"
  else
    echo "MediaMTX: stopped"
  fi

  if recorded_publisher_is_running; then
    local pid=""
    read -r pid <"${PID_FILE}"
    echo "FFmpeg: running (PID ${pid})"
  else
    echo "FFmpeg: stopped"
  fi

  if container_is_running && recorded_publisher_is_running; then
    echo "RTSP URL: $(public_rtsp_url)"
  fi
}

start_all() {
  local video_file="$1"
  local publish_url=""
  local publisher_pid=""

  require_command docker
  require_command ffmpeg
  require_command ffprobe
  require_command ps

  [[ "${RTSP_PORT}" =~ ^[0-9]+$ ]] || fail "CCTV_SAMPLE_RTSP_PORT must be numeric"
  ((RTSP_PORT >= 1 && RTSP_PORT <= 65535)) || fail "CCTV_SAMPLE_RTSP_PORT must be between 1 and 65535"
  [[ -n "${RTSP_PATH}" ]] || fail "CCTV_SAMPLE_RTSP_PATH must not be empty"
  [[ "${RTSP_PATH}" != /* ]] || fail "CCTV_SAMPLE_RTSP_PATH must not begin with '/'"
  [[ -f "${video_file}" ]] || fail "sample video not found: ${video_file}"

  if container_is_running && recorded_publisher_is_running; then
    echo "Sample RTSP stream is already running."
    echo "RTSP URL: $(public_rtsp_url)"
    return
  fi

  if container_exists || [[ -e "${PID_FILE}" ]]; then
    echo "Cleaning up an incomplete previous sample RTSP session."
    stop_publisher
    stop_server
  fi

  mkdir -p -- "${STATE_DIR}"
  publish_url="$(local_rtsp_url)"

  echo "Starting MediaMTX container ${CONTAINER_NAME}..."
  docker run \
    --rm \
    --detach \
    --name "${CONTAINER_NAME}" \
    --publish "${RTSP_PORT}:8554" \
    "${MEDIAMTX_IMAGE}" >/dev/null

  if ! wait_for_rtsp_server; then
    echo "MediaMTX did not become ready on port ${RTSP_PORT}." >&2
    docker logs "${CONTAINER_NAME}" >&2 || true
    stop_server
    exit 1
  fi

  echo "Publishing ${video_file}..."
  printf '%s\n' "${publish_url}" >"${URL_FILE}"
  nohup ffmpeg \
    -hide_banner \
    -loglevel warning \
    -nostdin \
    -re \
    -stream_loop -1 \
    -i "${video_file}" \
    -an \
    -c:v libx264 \
    -preset veryfast \
    -tune zerolatency \
    -pix_fmt yuv420p \
    -f rtsp \
    -rtsp_transport tcp \
    "${publish_url}" >"${FFMPEG_LOG}" 2>&1 &
  publisher_pid=$!
  printf '%s\n' "${publisher_pid}" >"${PID_FILE}"

  if ! wait_for_stream "${publish_url}"; then
    echo "FFmpeg did not publish a probeable RTSP stream." >&2
    if [[ -s "${FFMPEG_LOG}" ]]; then
      tail -n 30 "${FFMPEG_LOG}" >&2
    fi
    stop_publisher
    stop_server
    exit 1
  fi

  echo "Sample RTSP stream is ready."
  echo "RTSP URL: $(public_rtsp_url)"
  echo "FFmpeg log: ${FFMPEG_LOG}"
  echo
  echo "Run the blueprint with:"
  echo "  mn blueprint run --folder \"${BLUEPRINT_DIR}\" --set video_source.uri=$(public_rtsp_url) --debug --web-ui"
}

action="${1:-}"
case "${action}" in
  start)
    start_all "${2:-${CCTV_SAMPLE_VIDEO:-${BLUEPRINT_DIR}/examples/sample_inputs/sample.mp4}}"
    ;;
  stop)
    stop_all
    ;;
  status)
    print_status
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
