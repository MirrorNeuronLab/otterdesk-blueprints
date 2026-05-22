#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
from urllib.parse import urlparse


def main() -> int:
    uri = video_source_uri()
    parsed = urlparse(uri)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.netloc:
        return fail(
            "config.invalid_scheme",
            "video_source.uri must be an rtsp:// or rtsps:// URL",
            "Use an RTSP camera URL such as rtsp://camera-host/path.",
            actual=uri,
            status=2,
        )

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return fail(
            "validator.dependency_missing",
            "ffprobe is required to validate RTSP video streams",
            "Install ffmpeg/ffprobe on the runtime host or run with --force if you intentionally want to skip probing.",
            status=2,
        )

    command = [
        ffprobe,
        "-v",
        "error",
        "-rtsp_transport",
        os.environ.get("FFMPEG_RTSP_TRANSPORT", "tcp"),
        "-rw_timeout",
        str(int(float(os.environ.get("RTSP_VALIDATE_TIMEOUT_SECONDS", "5")) * 1_000_000)),
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        uri,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    if result.returncode != 0 or "video" not in result.stdout.lower():
        detail = (result.stderr or result.stdout or "no video stream reported").strip()
        return fail(
            "rtsp.unreachable",
            f"RTSP video stream is not reachable: {detail}",
            "Check the camera URL, credentials, network access, and whether the stream exposes a video track.",
            actual=uri,
            debug={"returncode": result.returncode, "detail": detail},
            status=1,
        )

    print(f"RTSP video stream validated: {uri}")
    return 0


def fail(
    code: str,
    message: str,
    help_text: str,
    *,
    actual: str | None = None,
    debug: dict | None = None,
    status: int = 1,
) -> int:
    issue = {
        "code": code,
        "message": message,
        "help": help_text,
        "severity": "error",
        "location": {
            "source": "config",
            "path": "video_source.uri",
            "pointer": "/config/video_source/uri",
        },
    }
    if actual is not None:
        issue["actual"] = redact_url(actual)
    if debug:
        issue["debug"] = {key: redact_url(str(value)) for key, value in debug.items()}
    print(json.dumps({
        "version": "validation.report/v1",
        "ok": False,
        "status": "failed",
        "error_count": 1,
        "errors": [message],
        "issues": [issue],
        "results": [],
    }, sort_keys=True))
    return status


def redact_url(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return parsed._replace(netloc=host, query="[redacted]" if parsed.query else "").geturl()


def video_source_uri() -> str:
    config = {}
    raw_config = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if raw_config:
        try:
            config = json.loads(raw_config)
        except json.JSONDecodeError:
            config = {}
    video_source = config.get("video_source") if isinstance(config, dict) else {}
    uri = video_source.get("uri") if isinstance(video_source, dict) else None
    return str(uri or os.environ.get("VIDEO_SOURCE_URI") or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
