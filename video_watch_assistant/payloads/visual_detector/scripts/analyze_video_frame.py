#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_VIDEO_SOURCE_URI = "rtsp://127.0.0.1:8554/video-watch"
LIVE_STREAM_SCHEMES = ("rtsp://", "rtsps://", "rtmp://", "rtmps://")


def load_json_env(name: str) -> dict[str, Any]:
    path = os.environ.get(name)
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text())


def initial_state() -> dict[str, Any]:
    return {
        "frames_seen": 0,
        "video_position_seconds": 0.0,
        "last_alert_wall_ts": 0.0,
        "detections": 0,
        "last_detection": None,
        "last_detection_report": None,
        "last_error": None,
    }


def resolve_source_uri(source_uri: str) -> str:
    source = source_uri.strip()
    source_path = source_path_from_uri(source)
    if source_path is None:
        return source_uri

    candidates = source_path_candidates(source_path)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return source_uri


def source_uri_with_host(source_uri: str, host: str) -> str:
    parsed = urllib.parse.urlsplit(source_uri)
    replacement_host = host
    if ":" in replacement_host and not replacement_host.startswith("["):
        replacement_host = f"[{replacement_host}]"

    userinfo = ""
    if "@" in parsed.netloc:
        userinfo = parsed.netloc.rsplit("@", 1)[0] + "@"

    try:
        port = parsed.port
    except ValueError:
        return source_uri
    if port is not None:
        replacement_host = f"{replacement_host}:{port}"
    return urllib.parse.urlunsplit((parsed.scheme, f"{userinfo}{replacement_host}", parsed.path, parsed.query, parsed.fragment))


def stream_fallback_sources(source_uri: str, fallback_hosts: list[str] | tuple[str, ...] | None = None) -> list[str]:
    parsed = urllib.parse.urlsplit(source_uri)
    scheme = parsed.scheme.lower()
    host = parsed.hostname
    if scheme not in {"rtsp", "rtsps", "rtmp", "rtmps"} or not host:
        return []

    if host not in {"127.0.0.1", "localhost", "::1"}:
        return []

    raw_hosts = fallback_hosts
    if raw_hosts is None:
        raw_hosts = [
            item.strip()
            for item in os.environ.get(
                "MN_HOST_STREAM_FALLBACK_HOSTS",
                "host.docker.internal,host.openshell.internal,192.168.65.254",
            ).split(",")
            if item.strip()
        ]

    candidates: list[str] = []
    for fallback_host in raw_hosts:
        candidate = source_uri_with_host(source_uri, fallback_host)
        if candidate != source_uri and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def local_demo_fallback_sources(source_uri: str) -> list[str]:
    parsed = urllib.parse.urlsplit(source_uri)
    if parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        return []
    if parsed.path.rstrip("/") != "/video-watch":
        return []

    candidates = [
        os.environ.get("LOCAL_DEMO_VIDEO_FILE", "").strip(),
        "data/sample.mp4",
        "/sandbox/job/visual_detector/data/sample.mp4",
    ]
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in result and Path(candidate).is_file():
            result.append(candidate)
    return result


def is_local_demo_fallback(candidate_source: str) -> bool:
    return candidate_source in local_demo_fallback_sources("rtsp://127.0.0.1:8554/video-watch")


def source_path_from_uri(source_uri: str) -> Path | None:
    parsed = urllib.parse.urlsplit(source_uri)
    if parsed.scheme and parsed.scheme != "file":
        return None
    if parsed.scheme == "file":
        path = urllib.request.url2pathname(parsed.path)
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            path = f"//{parsed.netloc}{path}"
        return Path(path)
    return Path(source_uri)


def source_path_candidates(source_path: Path) -> list[Path]:
    script_path = Path(__file__).resolve()
    detector_root = script_path.parents[1]
    blueprint_root = script_path.parents[3]
    raw = source_path.expanduser()
    candidates: list[Path] = []

    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend(
            [
                Path.cwd() / raw,
                detector_root / raw,
                blueprint_root / raw,
                blueprint_root / "payloads" / "visual_detector" / raw,
            ]
        )

    candidates.extend(remapped_payload_candidates(raw, detector_root, blueprint_root))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def remapped_payload_candidates(source_path: Path, detector_root: Path, blueprint_root: Path) -> list[Path]:
    parts = source_path.parts
    candidates: list[Path] = []

    payload_suffix = suffix_after(parts, ("payloads", "visual_detector"))
    if payload_suffix is not None:
        candidates.append(detector_root / payload_suffix)
        candidates.append(blueprint_root / "payloads" / "visual_detector" / payload_suffix)

    blueprint_suffix = suffix_after(parts, ("video_watch_assistant",))
    if blueprint_suffix is not None:
        candidates.append(blueprint_root / blueprint_suffix)
        nested_suffix = suffix_after(blueprint_suffix.parts, ("payloads", "visual_detector"))
        if nested_suffix is not None:
            candidates.append(detector_root / nested_suffix)

    return candidates


def suffix_after(parts: tuple[str, ...], marker: tuple[str, ...]) -> Path | None:
    marker_len = len(marker)
    for index in range(0, len(parts) - marker_len + 1):
        if parts[index : index + marker_len] == marker:
            suffix = parts[index + marker_len :]
            if suffix:
                return Path(*suffix)
    return None


def is_live_stream_source(source_uri: str) -> bool:
    return source_uri.strip().lower().startswith(LIVE_STREAM_SCHEMES)



def should_retry_with_docker_host_fallback(source_uri: str, error: str) -> bool:
    normalized = error.lower()
    return bool(stream_fallback_sources(source_uri)) and any(
        phrase in normalized
        for phrase in (
            "connection refused",
            "connection timed out",
            "connection to tcp",
            "failed to resolve",
            "resolve",
            "network is unreachable",
            "no route to host",
            "error opening input",
        )
    )


def should_rewind_file_source(source_uri: str, position_seconds: float, error: str) -> bool:
    if is_live_stream_source(source_uri) or position_seconds <= 0:
        return False
    normalized = error.lower()
    return any(
        phrase in normalized
        for phrase in (
            "ffmpeg failed",
            "empty frame",
            "produced no frame",
            "no frame",
            "end of file",
            "eof",
        )
    )


def ffmpeg_rtsp_transport() -> str:
    transport = os.environ.get("FFMPEG_RTSP_TRANSPORT", "tcp").strip().lower()
    if transport not in {"tcp", "udp"}:
        return "tcp"
    return transport


def ffmpeg_binary() -> str:
    configured = os.environ.get("FFMPEG_BINARY", "").strip()
    if configured:
        return configured
    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered
    try:
        import imageio_ffmpeg

        packaged = imageio_ffmpeg.get_ffmpeg_exe()
        if packaged:
            return packaged
    except Exception:
        pass
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if Path(candidate).is_file():
            return candidate
    return "ffmpeg"


def ffmpeg_frame_timeout_seconds() -> float:
    try:
        return max(1.0, float(os.environ.get("FFMPEG_FRAME_TIMEOUT_SECONDS", "8")))
    except ValueError:
        return 8.0


def extract_frame(source_uri: str, position_seconds: float, max_width: int) -> tuple[bytes, str]:
    resolved = resolve_source_uri(source_uri)
    suffix = Path(resolved).suffix.lower()
    if suffix in IMAGE_SUFFIXES and Path(resolved).exists():
        return Path(resolved).read_bytes(), "image/jpeg" if suffix in {".jpg", ".jpeg"} else mimetypes.guess_type(resolved)[0] or "image/png"

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    vf = f"scale='min({max_width},iw)':-2"
    try:
        last_error: str | None = None
        fallback_sources = [*stream_fallback_sources(resolved), *local_demo_fallback_sources(resolved)]
        sources = [resolved, *fallback_sources]

        for index, candidate_source in enumerate(sources):
            candidate_path = source_path_from_uri(candidate_source)
            if candidate_path is not None and candidate_path.suffix.lower() in IMAGE_SUFFIXES and candidate_path.exists():
                content_type = "image/jpeg" if candidate_path.suffix.lower() in {".jpg", ".jpeg"} else mimetypes.guess_type(str(candidate_path))[0] or "image/png"
                data = candidate_path.read_bytes()
                if data:
                    return data, content_type

            command = [
                ffmpeg_binary(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
            ]
            if is_live_stream_source(candidate_source):
                if candidate_source.lower().startswith(("rtsp://", "rtsps://")):
                    command.extend(["-rtsp_transport", ffmpeg_rtsp_transport()])
            elif is_local_demo_fallback(candidate_source):
                pass
            else:
                command.extend(["-ss", f"{position_seconds:.3f}"])

            command.extend(
                [
                    "-i",
                    candidate_source,
                    "-frames:v",
                    "1",
                    "-vf",
                    vf,
                    "-q:v",
                    "4",
                    "-y",
                    str(temp_path),
                ]
            )

            try:
                subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=ffmpeg_frame_timeout_seconds(),
                )
                data = temp_path.read_bytes()
                if not data:
                    last_error = f"ffmpeg produced an empty frame from {candidate_source}"
                    if index < len(sources) - 1:
                        continue
                    raise RuntimeError(last_error)
                return data, "image/jpeg"
            except subprocess.CalledProcessError as exc:
                last_error = exc.stderr.decode("utf-8", errors="replace").strip()
                if index < len(sources) - 1:
                    continue
                raise RuntimeError(f"ffmpeg failed to extract frame: {last_error}") from exc
            except subprocess.TimeoutExpired as exc:
                last_error = f"ffmpeg timed out extracting frame from {candidate_source}"
                if index < len(sources) - 1:
                    continue
                raise RuntimeError(last_error) from exc

        raise RuntimeError(f"ffmpeg failed to extract frame: {last_error or 'unknown error'}")
    except FileNotFoundError as exc:
        return extract_frame_with_cv2(resolved, position_seconds, max_width, exc)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def extract_frame_with_cv2(
    source_uri: str,
    position_seconds: float,
    max_width: int,
    ffmpeg_error: Exception | None = None,
) -> tuple[bytes, str]:
    try:
        import cv2
    except Exception as exc:
        if ffmpeg_error is not None:
            raise RuntimeError("ffmpeg or OpenCV is required to read video sources") from ffmpeg_error
        raise RuntimeError("OpenCV is required to read video sources without ffmpeg") from exc

    capture = cv2.VideoCapture(source_uri)
    if not capture.isOpened():
        raise RuntimeError(f"unable to open video source: {source_uri}")

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        if not is_live_stream_source(source_uri) and fps > 0 and position_seconds > 0:
            capture.set(cv2.CAP_PROP_POS_MSEC, position_seconds * 1000.0)

        ok, frame = capture.read()
        if not ok or frame is None:
            if position_seconds > 0:
                capture.set(cv2.CAP_PROP_POS_MSEC, 0.0)
                ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError("OpenCV produced no frame")

        height, width = frame.shape[:2]
        if width > max_width:
            target_height = max(1, int(height * (max_width / width)))
            frame = cv2.resize(frame, (max_width, target_height), interpolation=cv2.INTER_AREA)

        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            raise RuntimeError("OpenCV failed to encode frame as JPEG")
        return encoded.tobytes(), "image/jpeg"
    finally:
        capture.release()


def mock_detection(frame_seq: int) -> dict[str, Any]:
    detected = frame_seq % 4 in {2, 3}
    detections = (
        [
            {
                "label": "industrial equipment",
                "category": "equipment",
                "color": "orange",
                "position": "near the center of the monitored scene",
                "activity": "visible in the active work area",
                "confidence": 0.82,
            }
        ]
        if detected
        else []
    )
    return {
        "detected": detected,
        "detected_target": detected,
        "detection_count": len(detections),
        "detections": detections,
        "confidence": 0.82 if detected else 0.18,
        "summary": "Mock mode detected one notable equipment item in the monitored scene." if detected else "Mock mode sees no configured targets in the monitored scene.",
        "detection_report": "1 detection: orange industrial equipment in the active work area." if detected else "",
        "activity_description": "The detected item is visible in the active work area." if detected else "",
        "detected_types": ["equipment"] if detected else [],
        "detected_colors": ["orange"] if detected else [],
        "appearance_notes": ["Detection details are synthetic in mock mode."] if detected else [],
        "risk_level": "medium" if detected else "low",
        "visible_subjects": ["industrial equipment"] if detected else [],
    }


def call_ollama(frame: bytes, prompt: str) -> dict[str, Any]:
    base_url = (
        os.environ.get("VL_MODEL_BASE_URL")
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://192.168.4.173:11434"
    ).rstrip("/")
    model = os.environ.get("VL_MODEL_NAME") or os.environ.get("OLLAMA_MODEL") or "nemotron3:33b"
    timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90"))
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": os.environ.get("OLLAMA_THINK", "false").strip().lower() in {"1", "true", "yes", "on"},
        "images": [base64.b64encode(frame).decode("ascii")],
        "options": {
            "temperature": float(os.environ.get("OLLAMA_TEMPERATURE", "0.0")),
            "num_predict": int(os.environ.get("OLLAMA_NUM_PREDICT", "300")),
        },
    }
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ollama request failed: {exc}") from exc

    text = raw.get("response") or raw.get("message", {}).get("content") or raw.get("thinking") or ""
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return fallback_detection_from_model_text(text, f"non-json response: {exc}")
        try:
            result = json.loads(text[start : end + 1])
        except json.JSONDecodeError as nested_exc:
            return fallback_detection_from_model_text(text, f"malformed json response: {nested_exc}")
    return normalize_detection(result)


def fallback_detection_from_model_text(text: str, reason: str) -> dict[str, Any]:
    cleaned = " ".join(str(text or "").split())[:500]
    summary = cleaned or "The vision model returned an unreadable response."
    return normalize_detection(
        {
            "detected": False,
            "detected_target": False,
            "detection_count": 0,
            "detections": [],
            "confidence": 0.0,
            "summary": summary,
            "detection_report": f"Vision model response could not be parsed as strict JSON; {reason}.",
            "activity_description": summary,
            "detected_types": [],
            "detected_colors": [],
            "appearance_notes": ["Model response was not strict JSON."],
            "risk_level": "low",
            "visible_subjects": [],
        }
    )


def normalize_detection(result: dict[str, Any]) -> dict[str, Any]:
    confidence = result.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    detected = result.get("detected_target", result.get("detected", False))
    if isinstance(detected, str):
        detected = detected.strip().lower() in {"true", "yes", "1", "detected", "visible", "present", "active"}

    detections = result.get("detections", result.get("observed_items", []))
    if isinstance(detections, dict):
        detections = [detections]
    if not isinstance(detections, list):
        detections = []

    normalized_detections: list[dict[str, Any]] = []
    for item in detections[:20]:
        if isinstance(item, dict):
            label = str(item.get("label", item.get("name", item.get("type", "observed item")))).strip()[:80] or "observed item"
            normalized_detections.append(
                {
                    "label": label,
                    "category": str(item.get("category", item.get("type", label))).strip()[:80] or label,
                    "color": str(item.get("color", "unknown")).strip()[:60] or "unknown",
                    "position": str(item.get("position", item.get("location", ""))).strip()[:160],
                    "activity": str(item.get("activity", item.get("movement", ""))).strip()[:160],
                    "confidence": safe_confidence(item.get("confidence", confidence)),
                }
            )
        elif str(item).strip():
            normalized_detections.append(
                {
                    "label": str(item).strip()[:80],
                    "category": "observed item",
                    "color": "unknown",
                    "position": "",
                    "activity": "",
                    "confidence": safe_confidence(confidence),
                }
            )

    detection_count = result.get("detection_count", len(normalized_detections) if detected else 0)
    try:
        detection_count = max(0, int(detection_count))
    except (TypeError, ValueError):
        detection_count = len(normalized_detections) if detected else 0

    risk_level = str(result.get("risk_level", "low")).lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium" if detected else "low"

    summary = str(result.get("summary", "")).strip()
    if not summary:
        summary = f"{detection_count} configured target(s) were observed in the monitored scene." if detected else "No configured targets were observed in the monitored scene."

    detection_report = str(result.get("detection_report", result.get("description", ""))).strip()
    if not detection_report and detected:
        details = []
        for detection in normalized_detections:
            label = " ".join(
                part for part in [detection.get("color"), detection.get("label")] if part and part != "unknown"
            )
            details.append(label or detection.get("label") or "observed item")
        detection_report = f"{detection_count} detection(s): {', '.join(details)}." if details else summary

    activity_description = str(result.get("activity_description", result.get("activity", ""))).strip()
    if not activity_description and detected:
        activity_description = "Activity is not clearly visible."

    detected_types = result.get("detected_types", result.get("categories", []))
    if not isinstance(detected_types, list):
        detected_types = [str(detected_types)]
    if not detected_types and normalized_detections:
        detected_types = [detection["category"] for detection in normalized_detections]

    detected_colors = result.get("detected_colors", [])
    if not isinstance(detected_colors, list):
        detected_colors = [str(detected_colors)]
    if not detected_colors and normalized_detections:
        detected_colors = [detection["color"] for detection in normalized_detections if detection["color"]]

    appearance_notes = result.get("appearance_notes", [])
    if not isinstance(appearance_notes, list):
        appearance_notes = [str(appearance_notes)]

    visible_subjects = result.get("visible_subjects", [])
    if not isinstance(visible_subjects, list):
        visible_subjects = [str(visible_subjects)]

    return {
        "detected": bool(detected),
        "detected_target": bool(detected),
        "detection_count": detection_count,
        "detections": normalized_detections,
        "confidence": max(0.0, min(confidence, 1.0)),
        "summary": summary[:500],
        "detection_report": detection_report[:900],
        "activity_description": activity_description[:700],
        "detected_types": [str(item)[:80] for item in detected_types[:12] if str(item).strip()],
        "detected_colors": [str(item)[:60] for item in detected_colors[:12] if str(item).strip()],
        "appearance_notes": [str(item)[:120] for item in appearance_notes[:8] if str(item).strip()],
        "risk_level": risk_level,
        "visible_subjects": [str(item)[:80] for item in visible_subjects[:8]],
    }


def safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def detection_prompt(camera_id: str) -> str:
    target_description = os.environ.get(
        "VISUAL_DETECTION_TARGETS",
        "notable people, equipment, objects, hazards, access activity, workflow activity, or other user-defined subjects",
    )
    return os.environ.get(
        "VISUAL_DETECTION_PROMPT",
        (
            "You are monitoring a 24/7 video camera. Inspect the image and decide whether any configured "
            f"visual targets are present or active. Targets to watch for: {target_description}. Count only real "
            "visible subjects or activity; ignore shadows, reflections, signage text, static background clutter, "
            "and uncertain guesses unless they are directly relevant to the configured targets. For every detection, "
            "report the observable label, category, visible color if useful, position in the scene, and activity. "
            "Return only JSON with keys: detected boolean, detected_target boolean, detection_count integer, "
            "detections array of objects with label, category, color, position, activity, and confidence, confidence "
            "number from 0 to 1, summary short string, detection_report string, activity_description string, "
            "detected_types array of strings, detected_colors array of strings, appearance_notes array of strings, "
            f"risk_level one of low/medium/high, and visible_subjects array. Camera id: {camera_id}."
        ),
    )


def should_alert(detection: dict[str, Any], state: dict[str, Any]) -> bool:
    threshold = float(
        os.environ.get(
            "DETECTION_CONFIDENCE_THRESHOLD",
            "0.65",
        )
    )
    cooldown = float(os.environ.get("DETECTION_ALERT_COOLDOWN_SECONDS", "60"))
    if not detection.get("detected_target") or float(detection.get("confidence", 0)) < threshold:
        return False
    return time.time() - float(state.get("last_alert_wall_ts", 0.0)) >= cooldown


def post_slack(text: str) -> tuple[str, dict[str, Any]]:
    enabled = os.environ.get("SLACK_ALERT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    token = os.environ.get("MN_SLACK_BOT_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("MN_SLACK_DEFAULT_CHANNEL") or os.environ.get("SLACK_DEFAULT_CHANNEL")
    if not enabled:
        return "skipped", {"reason": "slack_disabled", "channel": channel}
    if not token:
        return "skipped", {"reason": "missing_slack_bot_token", "channel": channel}
    if not channel:
        return "skipped", {"reason": "missing_slack_channel", "channel": channel}

    api_url = os.environ.get("MN_SLACK_API_BASE_URL") or os.environ.get("SLACK_API_BASE_URL") or "https://slack.com/api/chat.postMessage"
    payload = {"channel": channel, "text": text}
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("ok") is True:
        return "sent", {"channel": channel, "ts": body.get("ts")}
    return "error", {"channel": channel, "error": body.get("error", "unknown_slack_error")}


def alert_text(camera_id: str, detection: dict[str, Any], frame_seq: int, source_uri: str) -> str:
    prefix = os.environ.get("SLACK_MESSAGE_PREFIX", "Video detection alert")
    detections = detection.get("detections") or []
    detection_lines = []
    for index, item in enumerate(detections[:8], start=1):
        detection_lines.append(
            f"{index}. {item.get('color', 'unknown')} {item.get('label', 'observed item')} - "
            f"{item.get('position') or 'position unclear'}; {item.get('activity') or 'activity unclear'}"
        )
    detection_text = "\n".join(detection_lines) if detection_lines else "No per-detection details reported."
    description = detection.get("detection_report") or detection["summary"]
    activity = detection.get("activity_description") or "Activity not clearly visible."
    return (
        f"{prefix}: {detection.get('detection_count', 0)} configured target(s) observed on {camera_id}\n"
        f"Confidence: {detection['confidence']:.2f} | Risk: {detection['risk_level']} | Frame: {frame_seq}\n"
        f"{description}\n"
        f"Activity: {activity}\n"
        f"Detection details:\n{detection_text}\n"
        f"Source: {source_uri}"
    )


def main() -> None:
    message = load_json_env("MN_MESSAGE_FILE")
    payload = load_json_env("MN_INPUT_FILE")
    context = load_json_env("MN_CONTEXT_FILE")
    state = context.get("agent_state") or initial_state()

    frame_seq = int(payload.get("tick_seq") or state.get("frames_seen", 0) + 1)
    camera_id = payload.get("camera_id") or os.environ.get("CAMERA_ID", "video-watch")
    source_uri = os.environ.get("VIDEO_SOURCE_URI", DEFAULT_VIDEO_SOURCE_URI)
    sample_seconds = float(os.environ.get("FRAME_SAMPLE_SECONDS", "10.0"))
    max_width = int(os.environ.get("FRAME_JPEG_MAX_WIDTH", "896"))

    events: list[dict[str, Any]] = []
    stream = message.get("stream") or {}

    try:
        position = float(state.get("video_position_seconds", 0.0))
        if os.environ.get("MOCK_VLM_DETECTION", "false").strip().lower() in {"1", "true", "yes", "on"}:
            detection = mock_detection(frame_seq)
        else:
            frame, _content_type = extract_frame(source_uri, position, max_width)
            detection = call_ollama(frame, detection_prompt(camera_id))

        detection_payload = {
            **detection,
            "camera_id": camera_id,
            "frame_seq": frame_seq,
            "video_position_seconds": round(position, 3),
            "source_uri": source_uri,
            "stream_id": stream.get("stream_id"),
        }
        if detection["detected_target"]:
            state["detections"] = int(state.get("detections", 0)) + 1
            state["last_detection"] = detection_payload
            state["last_detection_report"] = detection_payload.get("detection_report")
            events.append({"type": "video_watch_detection", "payload": detection_payload})

        if should_alert(detection, state):
            status, slack_payload = post_slack(alert_text(camera_id, detection, frame_seq, source_uri))
            event_type = "video_watch_slack_alert_sent" if status == "sent" else f"video_watch_slack_alert_{status}"
            events.append({"type": event_type, "payload": {**slack_payload, "frame_seq": frame_seq, "camera_id": camera_id}})
            if status in {"sent", "skipped"}:
                state["last_alert_wall_ts"] = time.time()

        state["last_error"] = None
        state["video_position_seconds"] = position + sample_seconds
        state["frames_seen"] = int(state.get("frames_seen", 0)) + 1
    except Exception as exc:
        message_text = str(exc)[:800]
        if should_rewind_file_source(source_uri, float(state.get("video_position_seconds", 0.0)), message_text):
            state["video_position_seconds"] = 0.0
            message_text = f"{message_text}; rewound source for next tick"
        state["last_error"] = message_text
        events.append(
            {
                "type": "video_watch_frame_analysis_failed",
                "payload": {
                    "camera_id": camera_id,
                    "frame_seq": frame_seq,
                    "source_uri": source_uri,
                    "error": message_text,
                },
            }
        )

    print(json.dumps({"next_state": state, "events": events}))


if __name__ == "__main__":
    main()
