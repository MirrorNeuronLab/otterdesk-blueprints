#!/usr/bin/env bash
set -euo pipefail

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "cctv_operator requires FFmpeg with CUDA/NVDEC support in its NVIDIA DockerWorker" >&2
  exit 2
fi

if ! ffmpeg -hide_banner -hwaccels 2>/dev/null | grep -qx 'cuda'; then
  echo "cctv_operator requires FFmpeg CUDA hardware acceleration" >&2
  exit 2
fi

export FFMPEG_BINARY="${FFMPEG_BINARY:-$(command -v ffmpeg)}"
export FFPROBE_BINARY="${FFPROBE_BINARY:-$(command -v ffprobe)}"
export CCTV_MEDIA_ACCELERATOR="nvidia_cuda"

exec python3 scripts/analyze_video_frame.py
