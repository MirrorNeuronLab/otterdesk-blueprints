"""Publish a bounded CCTV image for the shared conversation media widget."""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
from pathlib import Path


MAX_PREVIEW_BYTES = 75 * 1024


def publish_snapshot(run_dir: Path, image_path: Path, *, run_id: str,
                     camera_id: str, frame_seq: int) -> bool:
    if not run_id or not image_path.is_file():
        return False
    web_dir = run_dir / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    source = image_path.read_bytes()
    if len(source) <= MAX_PREVIEW_BYTES and source[:2] == b"\xff\xd8" and source[-2:] == b"\xff\xd9":
        preview = source
    else:
        preview = b""
        for quality in (8, 16, 24):
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                 "-vf", "scale=480:-2:flags=bicubic", "-frames:v", "1",
                 "-q:v", str(quality), "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                input=source, capture_output=True, timeout=15, check=False,
            )
            candidate = result.stdout
            if (result.returncode == 0 and 4 <= len(candidate) <= MAX_PREVIEW_BYTES
                    and candidate[:2] == b"\xff\xd8" and candidate[-2:] == b"\xff\xd9"):
                preview = candidate
                break
        if not preview:
            return False
    image_name = "cctv_snapshot.jpg"
    image_tmp = web_dir / ".cctv_snapshot.jpg.tmp"
    image_tmp.write_bytes(preview)
    os.replace(image_tmp, web_dir / image_name)
    manifest = {
        "schema": "otterdesk.conversation_media.v1",
        "run_id": run_id,
        "title": "Camera snapshot",
        "description": "Frame selected for the monitoring condition check.",
        "items": [{
            "type": "image", "mime_type": "image/jpeg", "filename": image_name,
            "sha256": hashlib.sha256(preview).hexdigest(),
            "title": f"Frame {frame_seq}", "alt": f"Selected CCTV frame {frame_seq} from {camera_id}",
            "caption": f"Camera {camera_id}; frame {frame_seq}. Review the original live stream before acting.",
        }],
    }
    manifest_tmp = web_dir / ".conversation_media.json.tmp"
    manifest_tmp.write_text(json.dumps(manifest), encoding="utf-8")
    os.replace(manifest_tmp, web_dir / "conversation_media.json")
    return True
