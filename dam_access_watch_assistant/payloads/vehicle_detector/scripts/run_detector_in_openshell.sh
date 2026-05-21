#!/usr/bin/env bash
set -euo pipefail

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required in the detector OpenShell sandbox image" >&2
  exit 2
fi

/usr/bin/python3 - <<'PY' >&2
import cv2

print(f"OpenCV {cv2.__version__} available in detector OpenShell sandbox")
PY

export FFMPEG_BINARY="${FFMPEG_BINARY:-$(command -v ffmpeg)}"
export LIVE_FRAME_FALLBACK_PATH="${LIVE_FRAME_FALLBACK_PATH:-/sandbox/live/latest.jpg}"
export LIVE_FRAME_FALLBACK_PREFER="${LIVE_FRAME_FALLBACK_PREFER:-true}"

exec /usr/bin/python3 scripts/analyze_dam_vehicle_frame.py
