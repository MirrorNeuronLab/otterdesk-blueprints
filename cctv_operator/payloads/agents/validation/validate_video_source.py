#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys


def _load_repo_env() -> None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "otterdesk_blueprint_env.py").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            from otterdesk_blueprint_env import load_blueprint_env

            load_blueprint_env(__file__)
            return


_load_repo_env()

from mn_live_video_analysis_skill import (
    probe_stream,
    redact_source_uri,
    validate_stream_uri,
)


BUNDLED_DEMO_PROFILE = "bundled_demo"
BUNDLED_DEMO_URI = "rtsp://127.0.0.1:8554/cctv-demo"


def main() -> int:
    config = blueprint_config()
    video_source = config.get("video_source") if isinstance(config.get("video_source"), dict) else {}
    mode = str(video_source.get("mode") or "stream").strip().lower()
    if mode != "stream":
        return fail(
            "config.invalid_source_mode",
            "video_source.mode must be stream",
            "CCTV Operator accepts one approved RTSP/RTMP stream.",
            actual=mode,
            path="video_source.mode",
            status=2,
        )

    uri = video_source_uri(video_source)
    profile = video_source_profile(video_source, uri)
    if profile not in {BUNDLED_DEMO_PROFILE, "external"}:
        return fail(
            "config.invalid_source_profile",
            "video_source.profile must be bundled_demo or external",
            "Keep bundled_demo for the self-contained demo, or use external with an approved RTSP/RTMP URI.",
            actual=profile,
            path="video_source.profile",
            status=2,
        )
    try:
        uri = validate_stream_uri(uri)
    except ValueError as exc:
        return fail(
            "config.invalid_scheme",
            str(exc),
            "Set video_source.uri to an approved CCTV stream URL.",
            actual=uri,
            status=2,
        )

    if profile == BUNDLED_DEMO_PROFILE:
        if uri != BUNDLED_DEMO_URI:
            return fail(
                "config.invalid_demo_uri",
                f"bundled demo source must use {BUNDLED_DEMO_URI}",
                "Keep the bundled demo URI, or set video_source.profile=external for a real CCTV stream.",
                actual=uri,
                status=2,
            )
        print(
            "Bundled CCTV demo source accepted; the shared NVIDIA "
            "DockerWorker will start and probe it before sampling."
        )
        return 0

    ffprobe_binary = str(
        os.environ.get("FFPROBE_BINARY") or shutil.which("ffprobe") or ""
    ).strip()
    if not ffprobe_binary:
        print(
            "Video stream URI accepted; reachability will be checked by "
            f"the scheduled NVIDIA worker: {redact_source_uri(uri)}"
        )
        return 0

    try:
        probe_stream(
            uri,
            timeout_seconds=float(
                os.environ.get("RTSP_VALIDATE_TIMEOUT_SECONDS", "5")
            ),
            rtsp_transport=os.environ.get("FFMPEG_RTSP_TRANSPORT", "tcp"),
        )
    except RuntimeError as exc:
        return fail(
            "stream.unreachable",
            str(exc),
            "Check the camera URL, credentials, network access, FFmpeg installation, and whether the stream exposes a video track.",
            actual=uri,
            status=1,
        )

    print(f"Video stream validated: {redact_source_uri(uri)}")
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
        issue["actual"] = redact_source_uri(actual)
    if debug:
        issue["debug"] = {
            key: redact_source_uri(str(value)) for key, value in debug.items()
        }
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


def video_source_profile(video_source: dict, uri: str) -> str:
    profile = (
        video_source.get("profile")
        if isinstance(video_source, dict)
        else None
    )
    if profile is None and uri == BUNDLED_DEMO_URI:
        return BUNDLED_DEMO_PROFILE
    return str(profile or "external").strip().lower()


if __name__ == "__main__":
    raise SystemExit(main())
