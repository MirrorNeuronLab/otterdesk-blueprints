#!/usr/bin/env bash
set -euo pipefail

readonly DEMO_ROOT="/opt/cctv-demo"
readonly STATE_DIR="/run/cctv-demo"
readonly SERVER_PID_FILE="${STATE_DIR}/mediamtx.pid"
readonly PUBLISHER_PID_FILE="${STATE_DIR}/ffmpeg.pid"
readonly SERVER_LOG="${STATE_DIR}/mediamtx.log"
readonly PUBLISHER_LOG="${STATE_DIR}/ffmpeg.log"
readonly STREAM_URI="rtsp://127.0.0.1:8554/cctv-demo"

pid_is_running() {
  local pid_file="$1"
  local pid=""
  [[ -r "${pid_file}" ]] || return 1
  read -r pid <"${pid_file}" || return 1
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

stop_recorded_process() {
  local pid_file="$1"
  local pid=""
  if [[ -r "${pid_file}" ]]; then
    read -r pid <"${pid_file}" || true
  fi
  if [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
  fi
  rm -f -- "${pid_file}"
}

cleanup_failed_start() {
  stop_recorded_process "${PUBLISHER_PID_FILE}"
  stop_recorded_process "${SERVER_PID_FILE}"
}

wait_for_server() {
  for _ in {1..40}; do
    if (exec 3<>/dev/tcp/127.0.0.1/8554) 2>/dev/null; then
      return 0
    fi
    pid_is_running "${SERVER_PID_FILE}" || return 1
    sleep 0.25
  done
  return 1
}

wait_for_stream() {
  for _ in {1..40}; do
    if ffprobe \
      -v error \
      -rtsp_transport tcp \
      -show_entries stream=codec_name,width,height \
      -of default=noprint_wrappers=1 \
      "${STREAM_URI}" >/dev/null 2>&1; then
      return 0
    fi
    pid_is_running "${PUBLISHER_PID_FILE}" || return 1
    sleep 0.5
  done
  return 1
}

command -v mediamtx >/dev/null 2>&1 || {
  echo "cctv demo source requires MediaMTX in the DockerWorker image" >&2
  exit 2
}
command -v ffmpeg >/dev/null 2>&1 || {
  echo "cctv demo source requires FFmpeg in the DockerWorker image" >&2
  exit 2
}
command -v ffprobe >/dev/null 2>&1 || {
  echo "cctv demo source requires FFprobe in the DockerWorker image" >&2
  exit 2
}
[[ -s "${DEMO_ROOT}/sample.mp4" ]] || {
  echo "cctv demo source fixture is missing from the DockerWorker image" >&2
  exit 2
}

mkdir -p -- "${STATE_DIR}"
if pid_is_running "${SERVER_PID_FILE}" && \
   pid_is_running "${PUBLISHER_PID_FILE}"; then
  exit 0
fi

cleanup_failed_start
trap cleanup_failed_start ERR INT TERM

nohup mediamtx "${DEMO_ROOT}/mediamtx.yml" \
  </dev/null >"${SERVER_LOG}" 2>&1 &
printf '%s\n' "$!" >"${SERVER_PID_FILE}"

if ! wait_for_server; then
  echo "bundled CCTV demo MediaMTX server did not become ready" >&2
  tail -n 30 "${SERVER_LOG}" >&2 || true
  cleanup_failed_start
  exit 1
fi

nohup ffmpeg \
  -hide_banner \
  -loglevel warning \
  -nostdin \
  -re \
  -stream_loop -1 \
  -i "${DEMO_ROOT}/sample.mp4" \
  -an \
  -vf scale=-2:720,fps=15 \
  -c:v libx264 \
  -preset veryfast \
  -tune zerolatency \
  -g 30 \
  -keyint_min 30 \
  -sc_threshold 0 \
  -pix_fmt yuv420p \
  -f rtsp \
  -rtsp_transport tcp \
  "${STREAM_URI}" </dev/null >"${PUBLISHER_LOG}" 2>&1 &
printf '%s\n' "$!" >"${PUBLISHER_PID_FILE}"

if ! wait_for_stream; then
  echo "bundled CCTV demo publisher did not produce a probeable RTSP stream" >&2
  tail -n 30 "${PUBLISHER_LOG}" >&2 || true
  cleanup_failed_start
  exit 1
fi

trap - ERR INT TERM
echo "Bundled CCTV demo stream ready at ${STREAM_URI}" >&2
