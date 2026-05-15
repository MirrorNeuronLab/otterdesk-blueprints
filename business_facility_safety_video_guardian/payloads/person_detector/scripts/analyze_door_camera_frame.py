#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_VIDEO_SOURCE_URI = "rtsp://host.docker.internal:8554/local-camera"
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
        "last_human_description": None,
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
                blueprint_root / "payloads" / "person_detector" / raw,
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

    payload_suffix = suffix_after(parts, ("payloads", "person_detector"))
    if payload_suffix is not None:
        candidates.append(detector_root / payload_suffix)
        candidates.append(blueprint_root / "payloads" / "person_detector" / payload_suffix)

    blueprint_suffix = suffix_after(parts, ("business_facility_safety_video_guardian",))
    if blueprint_suffix is not None:
        candidates.append(blueprint_root / blueprint_suffix)
        nested_suffix = suffix_after(blueprint_suffix.parts, ("payloads", "person_detector"))
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


def source_uri_with_host(parsed: urllib.parse.SplitResult, host: str) -> str:
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo = f"{userinfo}:{parsed.password}"
        userinfo = f"{userinfo}@"

    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, f"{userinfo}{host}", parsed.path, parsed.query, parsed.fragment))


def docker_host_fallback_sources(source_uri: str) -> list[str]:
    parsed = urllib.parse.urlsplit(source_uri)
    if parsed.hostname != "host.docker.internal":
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    try:
        for family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
            "host.docker.internal",
            parsed.port or 0,
            socket.AF_INET,
            socket.SOCK_STREAM,
        ):
            if family != socket.AF_INET:
                continue
            host = sockaddr[0]
            if host in seen:
                continue
            seen.add(host)
            candidates.append(source_uri_with_host(parsed, host))
    except OSError:
        pass

    gateway_hosts = os.environ.get("MN_DOCKER_HOST_GATEWAY_IPS", "192.168.65.254")
    for host in [item.strip() for item in gateway_hosts.split(",") if item.strip()]:
        if host in seen:
            continue
        seen.add(host)
        candidates.append(source_uri_with_host(parsed, host))

    local_source = source_uri_with_host(parsed, "127.0.0.1")
    if local_source not in candidates:
        candidates.append(local_source)
    return candidates


def local_stream_host_fallback_sources(source_uri: str) -> list[str]:
    parsed = urllib.parse.urlsplit(source_uri)
    if not is_live_stream_source(source_uri) or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    hosts = os.environ.get(
        "MN_HOST_STREAM_FALLBACK_HOSTS",
        "host.docker.internal,host.openshell.internal,192.168.65.254",
    )
    for host in [item.strip() for item in hosts.split(",") if item.strip()]:
        if host in seen:
            continue
        seen.add(host)
        candidates.append(source_uri_with_host(parsed, host))
    return candidates


def live_frame_bridge_fallback_sources(source_uri: str) -> list[str]:
    if not is_live_stream_source(source_uri):
        return []
    frame_path = Path(os.environ.get("LIVE_FRAME_FALLBACK_PATH", "/sandbox/live/latest.jpg"))
    if frame_path.is_file() and frame_path.stat().st_size > 0:
        return [str(frame_path)]
    return []


def stream_fallback_sources(source_uri: str) -> list[str]:
    candidates = (
        live_frame_bridge_fallback_sources(source_uri)
        + docker_host_fallback_sources(source_uri)
        + local_stream_host_fallback_sources(source_uri)
    )
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate == source_uri or candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


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
        fallback_sources = stream_fallback_sources(resolved)
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
                    raise RuntimeError("ffmpeg produced an empty frame")
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
    return {
        "face_detected": detected,
        "person_detected": detected,
        "confidence": 0.82 if detected else 0.18,
        "summary": "Mock mode detected a visible person near the door." if detected else "Mock mode sees no person at the door.",
        "human_description": (
            "A person is visible near the camera; mock mode does not infer identity or private traits."
            if detected
            else ""
        ),
        "activity_description": "The person appears to be standing near the doorway." if detected else "",
        "face_description": (
            "A face is visible near the camera with a neutral expression; mock mode does not infer identity."
            if detected
            else ""
        ),
        "facial_features": ["visible face", "neutral expression"] if detected else [],
        "appearance_notes": ["Face details are synthetic in mock mode."] if detected else [],
        "risk_level": "medium" if detected else "low",
        "visible_subjects": ["face"] if detected else [],
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
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError(f"ollama returned non-json response: {text[:300]}")
        result = json.loads(text[start : end + 1])
    return normalize_detection(result)


def normalize_detection(result: dict[str, Any]) -> dict[str, Any]:
    confidence = result.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    detected = result.get("face_detected", result.get("person_detected", False))
    if isinstance(detected, str):
        detected = detected.strip().lower() in {"true", "yes", "1", "face", "person", "detected", "visible"}

    risk_level = str(result.get("risk_level", "low")).lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium" if detected else "low"

    summary = str(result.get("summary", "")).strip()
    if not summary:
        summary = "A person is visible near the door." if detected else "No person is visible near the door."

    human_description = str(result.get("human_description", result.get("person_description", ""))).strip()
    if not human_description and detected:
        human_description = summary

    activity_description = str(result.get("activity_description", result.get("what_the_person_is_doing", ""))).strip()
    if not activity_description and detected:
        activity_description = "The person's activity is not clearly visible."

    face_description = str(result.get("face_description", "")).strip()
    if not face_description and detected:
        face_description = human_description

    facial_features = result.get("facial_features", [])
    if not isinstance(facial_features, list):
        facial_features = [str(facial_features)]

    appearance_notes = result.get("appearance_notes", [])
    if not isinstance(appearance_notes, list):
        appearance_notes = [str(appearance_notes)]

    visible_subjects = result.get("visible_subjects", [])
    if not isinstance(visible_subjects, list):
        visible_subjects = [str(visible_subjects)]

    return {
        "face_detected": bool(detected),
        "person_detected": bool(detected),
        "confidence": max(0.0, min(confidence, 1.0)),
        "summary": summary[:500],
        "human_description": human_description[:700],
        "activity_description": activity_description[:700],
        "face_description": face_description[:700],
        "facial_features": [str(item)[:120] for item in facial_features[:12] if str(item).strip()],
        "appearance_notes": [str(item)[:120] for item in appearance_notes[:8] if str(item).strip()],
        "risk_level": risk_level,
        "visible_subjects": [str(item)[:80] for item in visible_subjects[:8]],
    }


def detection_prompt(camera_id: str) -> str:
    return os.environ.get(
        "HUMAN_DETECTION_PROMPT",
        os.environ.get(
            "PERSON_DETECTION_PROMPT",
            (
                "You are monitoring a 24/7 door camera for safety. Inspect the image and decide whether a "
                "human person is visible anywhere in the frame. Only trigger a positive result when a real "
                "person is visible; ignore posters, reflections, shadows, and empty background. If a person is "
                "visible, describe only observable, non-identifying appearance details such as clothing, pose, "
                "position in the scene, visible accessories, lighting/occlusion, and what the person appears "
                "to be doing. "
                "Do not identify the person, compare them to a known person, infer sensitive attributes, or "
                "guess age, gender, race, ethnicity, health, emotion beyond visible expression, or any private "
                "trait. Return only JSON with keys: person_detected boolean, face_detected boolean, confidence "
                "number from 0 to 1, summary short string, human_description string, activity_description "
                "string, face_description string, facial_features array of strings, appearance_notes array of "
                f"strings, risk_level one of low/medium/high, and visible_subjects array. Camera id: {camera_id}."
            ),
        ),
    )


def should_alert(detection: dict[str, Any], state: dict[str, Any]) -> bool:
    threshold = float(
        os.environ.get(
            "FACE_DETECTION_CONFIDENCE_THRESHOLD",
            os.environ.get("PERSON_DETECTION_CONFIDENCE_THRESHOLD", "0.65"),
        )
    )
    cooldown = float(os.environ.get("FACE_ALERT_COOLDOWN_SECONDS", os.environ.get("PERSON_ALERT_COOLDOWN_SECONDS", "60")))
    if not detection.get("person_detected") or float(detection.get("confidence", 0)) < threshold:
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
    prefix = os.environ.get("SLACK_MESSAGE_PREFIX", "Door camera human alert")
    features = detection.get("facial_features") or []
    feature_text = ", ".join(str(item) for item in features[:6]) if features else "No specific visible features reported."
    description = detection.get("human_description") or detection.get("face_description") or detection["summary"]
    activity = detection.get("activity_description") or "Activity not clearly visible."
    return (
        f"{prefix}: human detected on {camera_id}\n"
        f"Confidence: {detection['confidence']:.2f} | Risk: {detection['risk_level']} | Frame: {frame_seq}\n"
        f"{description}\n"
        f"Activity: {activity}\n"
        f"Visible features: {feature_text}\n"
        f"Source: {source_uri}"
    )


def main() -> None:
    message = load_json_env("MN_MESSAGE_FILE")
    payload = load_json_env("MN_INPUT_FILE")
    context = load_json_env("MN_CONTEXT_FILE")
    state = context.get("agent_state") or initial_state()

    frame_seq = int(payload.get("tick_seq") or state.get("frames_seen", 0) + 1)
    camera_id = payload.get("camera_id") or os.environ.get("CAMERA_ID", "front-door")
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
        if detection["person_detected"]:
            state["detections"] = int(state.get("detections", 0)) + 1
            state["last_detection"] = detection_payload
            state["last_human_description"] = detection_payload.get("human_description")
            events.append({"type": "door_camera_human_detected", "payload": detection_payload})

        if should_alert(detection, state):
            status, slack_payload = post_slack(alert_text(camera_id, detection, frame_seq, source_uri))
            event_type = "door_camera_slack_alert_sent" if status == "sent" else f"door_camera_slack_alert_{status}"
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
                "type": "door_camera_frame_analysis_failed",
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
