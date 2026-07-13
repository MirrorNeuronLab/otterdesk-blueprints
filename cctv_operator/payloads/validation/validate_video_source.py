#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlparse


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts", ".mts"}
STREAM_SCHEMES = {"rtsp", "rtsps", "rtmp", "rtmps"}


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
    mode = str(video_source.get("mode") or "folder").strip().lower()
    if mode == "folder":
        return validate_video_folder(config, video_source)
    if mode != "stream":
        return fail(
            "config.invalid_source_mode",
            "video_source.mode must be either folder or stream",
            "Choose folder for staged local videos or stream for an RTSP/RTMP source.",
            actual=mode,
            path="video_source.mode",
            status=2,
        )

    uri = video_source_uri(video_source)
    parsed = urlparse(uri)
    if parsed.scheme.lower() not in STREAM_SCHEMES or not parsed.netloc:
        return fail(
            "config.invalid_scheme",
            "stream mode requires an rtsp://, rtsps://, rtmp://, or rtmps:// URL",
            "Set video_source.uri to an approved CCTV stream URL.",
            actual=uri,
            status=2,
        )

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return fail(
            "validator.dependency_missing",
            "ffprobe is required to validate RTSP/RTMP video streams",
            "Install ffmpeg/ffprobe on the runtime host or run with --force if you intentionally want to skip probing.",
            status=2,
        )

    return validate_stream(ffprobe, uri)


def validate_video_folder(config: dict, video_source: dict) -> int:
    raw_folder = str(
        video_source.get("folder_path")
        or config.get("inputs", {}).get("payload", {}).get("input_folder")
        or "cctv_operator/examples/sample_inputs"
    ).strip()
    folder = resolve_folder_path(raw_folder)
    if not folder.is_dir():
        return fail(
            "video_folder.missing",
            f"video folder is not available: {folder}",
            "Choose a readable folder containing approved video files.",
            actual=str(folder),
            path="video_source.folder_path",
            status=1,
        )
    videos = sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        return fail(
            "video_folder.empty",
            f"video folder contains no supported video files: {folder}",
            "Add MP4, MOV, MKV, AVI, WebM, M4V, TS, or MTS files.",
            actual=str(folder),
            path="video_source.folder_path",
            status=1,
        )
    print(f"Video folder validated: {folder} ({len(videos)} supported file(s))")
    return 0


def resolve_folder_path(raw_folder: str) -> Path:
    raw = Path(raw_folder).expanduser()
    if raw.is_absolute():
        return raw

    blueprint_root = Path(__file__).resolve().parents[2]
    candidates = [Path.cwd() / raw, blueprint_root / raw, blueprint_root.parent / raw]
    if raw.parts and raw.parts[0] == blueprint_root.name and len(raw.parts) > 1:
        candidates.insert(1, blueprint_root.joinpath(*raw.parts[1:]))
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return candidates[0].resolve()


def validate_stream(ffprobe: str, uri: str) -> int:
    command = [
        ffprobe,
        "-v",
        "error",
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
    if uri.lower().startswith(("rtsp://", "rtsps://")):
        command[3:3] = ["-rtsp_transport", os.environ.get("FFMPEG_RTSP_TRANSPORT", "tcp")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    if result.returncode != 0 or "video" not in result.stdout.lower():
        detail = (result.stderr or result.stdout or "no video stream reported").strip()
        return fail(
            "stream.unreachable",
            f"video stream is not reachable: {detail}",
            "Check the camera URL, credentials, network access, and whether the stream exposes a video track.",
            actual=uri,
            debug={"returncode": result.returncode, "detail": detail},
            status=1,
        )

    print(f"Video stream validated: {redact_url(uri)}")
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


if __name__ == "__main__":
    raise SystemExit(main())
