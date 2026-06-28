#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlparse


def _load_repo_env() -> None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "otterdesk_blueprint_env.py").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            from otterdesk_blueprint_env import load_blueprint_env

            load_blueprint_env(__file__)
            return


_load_repo_env()


def main() -> int:
    config = blueprint_config()
    video_source = config.get("video_source") if isinstance(config.get("video_source"), dict) else {}
    uri = video_source_uri(video_source)
    parsed = urlparse(uri)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.netloc:
        return fail(
            "config.invalid_scheme",
            "video_source.uri must be an rtsp:// or rtsps:// URL",
            "Use an RTSP camera URL such as rtsp://camera-host/path.",
            actual=uri,
            status=2,
        )

    if is_mapped_demo_endpoint(uri):
        ffprobe = shutil.which("ffprobe")
        return validate_demo_video(ffprobe, video_source)

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return fail(
            "validator.dependency_missing",
            "ffprobe is required to validate external RTSP video streams",
            "Install ffmpeg/ffprobe on the runtime host or run with --force if you intentionally want to skip probing.",
            status=2,
        )

    return validate_rtsp_stream(ffprobe, uri)


def validate_demo_video(ffprobe: str | None, video_source: dict) -> int:
    raw_demo = str(video_source.get("demo_video") or os.environ.get("DEMO_VIDEO_FILE") or "data/sample.mp4").strip()
    demo_path = Path(raw_demo)
    if not demo_path.is_absolute():
        demo_path = Path.cwd() / demo_path
    if not demo_path.is_file():
        if is_submitted_runtime_bundle():
            print(f"Mapped RTSP demo endpoint selected; bundled demo file is validated by the host pre-launch hook: {demo_path}")
            return 0
        return fail(
            "demo_video.missing",
            f"Demo video file is not available: {demo_path}",
            "Keep video_source.demo_video pointed at a readable bundled video file.",
            actual=str(demo_path),
            path="video_source.demo_video",
            status=1,
        )

    if not ffprobe:
        print(f"Demo video exists for mapped RTSP endpoint: {demo_path}")
        return 0

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(demo_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    if result.returncode != 0 or "video" not in result.stdout.lower():
        detail = (result.stderr or result.stdout or "no video stream reported").strip()
        return fail(
            "demo_video.invalid",
            f"Demo video file does not expose a readable video track: {detail}",
            "Replace video_source.demo_video with a readable video file.",
            actual=str(demo_path),
            debug={"returncode": result.returncode, "detail": detail},
            path="video_source.demo_video",
            status=1,
        )

    print(f"Demo video validated for mapped RTSP endpoint: {demo_path}")
    return 0


def validate_rtsp_stream(ffprobe: str, uri: str) -> int:
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
    path: str = "video_source.uri",
    status: int = 1,
) -> int:
    issue = {
        "code": code,
        "message": message,
        "help": help_text,
        "severity": "error",
        "location": {
            "source": "config",
            "path": path,
            "pointer": "/config/" + path.replace(".", "/"),
        },
    }
    if actual is not None:
        issue["actual"] = redact_url(actual)
    if debug:
        issue["debug"] = {key: redact_url(str(value)) for key, value in debug.items()}
    print(json.dumps({
        "version": 1,
        "schema_version": "validation.report/v1",
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


def is_mapped_demo_endpoint(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme not in {"rtsp", "rtsps"}:
        return False
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return False
    return parsed.path.rstrip("/") == "/video-watch"


def blueprint_config() -> dict:
    raw_config = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if raw_config:
        try:
            parsed = json.loads(raw_config)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def video_source_uri(video_source: dict) -> str:
    uri = video_source.get("uri") if isinstance(video_source, dict) else None
    return str(uri or os.environ.get("VIDEO_SOURCE_URI") or "").strip()


def is_submitted_runtime_bundle() -> bool:
    cwd = Path.cwd()
    return cwd.name.startswith("bundle_") and cwd.parent == Path("/tmp")


if __name__ == "__main__":
    raise SystemExit(main())
