#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_VIDEO_SOURCE_URI = "rtsp://127.0.0.1:8554/local-camera"


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
        "last_error": None,
    }


def resolve_source_uri(source_uri: str) -> str:
    source = Path(source_uri)
    if source.is_absolute() or "://" in source_uri:
        return source_uri

    candidates = [
        Path.cwd() / source,
        Path(__file__).resolve().parents[3] / source,
        Path(__file__).resolve().parents[4] / source,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return source_uri


def extract_frame(source_uri: str, position_seconds: float, max_width: int) -> tuple[bytes, str]:
    resolved = resolve_source_uri(source_uri)
    suffix = Path(resolved).suffix.lower()
    if suffix in IMAGE_SUFFIXES and Path(resolved).exists():
        return Path(resolved).read_bytes(), "image/jpeg" if suffix in {".jpg", ".jpeg"} else mimetypes.guess_type(resolved)[0] or "image/png"

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    vf = f"scale='min({max_width},iw)':-2"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        f"{position_seconds:.3f}",
        "-i",
        resolved,
        "-frames:v",
        "1",
        "-vf",
        vf,
        "-q:v",
        "4",
        "-y",
        str(temp_path),
    ]

    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        data = temp_path.read_bytes()
        if not data:
            raise RuntimeError("ffmpeg produced an empty frame")
        return data, "image/jpeg"
    except FileNotFoundError as exc:
        return extract_frame_with_cv2(resolved, position_seconds, max_width, exc)
    except subprocess.CalledProcessError as exc:
        error = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg failed to extract frame: {error}") from exc
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
        if fps > 0 and position_seconds > 0:
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
        "person_detected": detected,
        "confidence": 0.82 if detected else 0.18,
        "summary": "Mock mode detected a person near the door." if detected else "Mock mode sees no person at the door.",
        "risk_level": "medium" if detected else "low",
        "visible_subjects": ["person"] if detected else [],
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

    detected = result.get("person_detected", False)
    if isinstance(detected, str):
        detected = detected.strip().lower() in {"true", "yes", "1", "person", "detected"}

    risk_level = str(result.get("risk_level", "low")).lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium" if detected else "low"

    summary = str(result.get("summary", "")).strip()
    if not summary:
        summary = "A person is visible near the door." if detected else "No person is visible near the door."

    visible_subjects = result.get("visible_subjects", [])
    if not isinstance(visible_subjects, list):
        visible_subjects = [str(visible_subjects)]

    return {
        "person_detected": bool(detected),
        "confidence": max(0.0, min(confidence, 1.0)),
        "summary": summary[:500],
        "risk_level": risk_level,
        "visible_subjects": [str(item)[:80] for item in visible_subjects[:8]],
    }


def detection_prompt(camera_id: str) -> str:
    return os.environ.get(
        "PERSON_DETECTION_PROMPT",
        (
            "You are monitoring a 24/7 door camera for safety. Inspect the image and decide whether any person "
            "is visible anywhere in the frame. Return only JSON with keys: person_detected boolean, confidence "
            "number from 0 to 1, summary short string, risk_level one of low/medium/high, and visible_subjects "
            f"array. Camera id: {camera_id}."
        ),
    )


def should_alert(detection: dict[str, Any], state: dict[str, Any]) -> bool:
    threshold = float(os.environ.get("PERSON_DETECTION_CONFIDENCE_THRESHOLD", "0.65"))
    cooldown = float(os.environ.get("PERSON_ALERT_COOLDOWN_SECONDS", "60"))
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
    prefix = os.environ.get("SLACK_MESSAGE_PREFIX", "Door camera safety alert")
    return (
        f"{prefix}: person detected on {camera_id}\n"
        f"Confidence: {detection['confidence']:.2f} | Risk: {detection['risk_level']} | Frame: {frame_seq}\n"
        f"{detection['summary']}\n"
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
    sample_seconds = float(os.environ.get("FRAME_SAMPLE_SECONDS", "5.0"))
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
        events.append({"type": "door_camera_frame_analyzed", "payload": detection_payload})

        if detection["person_detected"]:
            state["detections"] = int(state.get("detections", 0)) + 1
            state["last_detection"] = detection_payload
            events.append({"type": "door_camera_person_detected", "payload": detection_payload})

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
        if "ffmpeg failed" in message_text and float(state.get("video_position_seconds", 0.0)) > 0:
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
