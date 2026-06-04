#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from mn_blueprint_support import start_agent_beacon_thread
except Exception:  # pragma: no cover - optional runtime support
    def start_agent_beacon_thread(message: str | None = None) -> None:
        return None

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
        "last_human_notice_wall_ts": 0.0,
        "last_human_notice_signature": None,
        "detections": 0,
        "last_detection": None,
        "last_detection_report": None,
        "last_observation": None,
        "recent_observations": [],
        "attention_instruction": "",
        "attention_targets": [],
        "last_attention_update": None,
        "conversation_context": {
            "what_happened": "No video frames have been analyzed yet.",
            "attention_instruction": "",
            "recent_observations": [],
        },
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
    provider = (
        os.environ.get("MN_VLM_PROVIDER")
        or os.environ.get("MN_LLM_PROVIDER")
        or os.environ.get("VL_MODEL_PROVIDER")
        or "docker_model_runner"
    ).strip().lower().replace("-", "_")
    base_url = _normalize_model_api_base(
        os.environ.get("MN_VLM_API_BASE")
        or os.environ.get("MN_LLM_API_BASE")
        or os.environ.get("VL_MODEL_BASE_URL")
        or os.environ.get("OLLAMA_BASE_URL")
        or ("http://localhost:11434" if provider == "ollama" else "http://localhost:12434/engines/v1"),
        provider=provider,
    )
    model = _normalize_vlm_model(
        os.environ.get("MN_VLM_MODEL")
        or os.environ.get("MN_LLM_MODEL")
        or os.environ.get("VL_MODEL_NAME")
        or os.environ.get("OLLAMA_MODEL")
        or "otterdesk-video-watch:default"
    )
    timeout = float(os.environ.get("MN_VLM_TIMEOUT_SECONDS") or os.environ.get("MN_LLM_TIMEOUT_SECONDS") or os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90"))
    if _uses_openai_compatible_runtime(provider, base_url):
        encoded = base64.b64encode(frame).decode("ascii")
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                    ],
                }
            ],
            "max_tokens": int(os.environ.get("MN_VLM_MAX_TOKENS") or os.environ.get("MN_LLM_MAX_TOKENS") or os.environ.get("OLLAMA_NUM_PREDICT", "300")),
            "temperature": float(os.environ.get("MN_VLM_TEMPERATURE") or os.environ.get("OLLAMA_TEMPERATURE", "0.0")),
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"model runner request failed: {exc}") from exc
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") if isinstance(choice, dict) else {}
        text = str((message or {}).get("content") or "")
        result, parse_error = parse_model_json(text)
        if result is None:
            return fallback_detection_from_model_text(text, parse_error)
        return normalize_detection(result)

    payload = {
        "model": model.removeprefix("ollama/"),
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
        raise RuntimeError(f"legacy Ollama request failed: {exc}") from exc

    text = raw.get("response") or raw.get("message", {}).get("content") or raw.get("thinking") or ""
    result, parse_error = parse_model_json(text)
    if result is None:
        return fallback_detection_from_model_text(text, parse_error)
    return normalize_detection(result)


def _normalize_vlm_model(model: str) -> str:
    value = str(model or "").strip()
    if value.lower() in {"", "default", "otterdesk-video-watch:default", "video-watch:default"}:
        return os.environ.get("MN_LLM_RUNTIME_MODEL") or "hf.co/nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16"
    if value.lower() in {"gemma4", "gemme4", "gemma4:e2b", "gemme4:e2b"}:
        return "ai/gemma4:E2B"
    return value


def _normalize_model_api_base(api_base: str, *, provider: str) -> str:
    value = str(api_base or "").strip().rstrip("/")
    if not value:
        return "http://localhost:11434" if provider == "ollama" else "http://localhost:12434/engines/v1"
    if "/engines/" in value:
        if value.endswith("/chat/completions"):
            value = value[: -len("/chat/completions")]
        return value.rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value.rstrip("/")


def _uses_openai_compatible_runtime(provider: str, api_base: str) -> bool:
    return provider in {"docker_model_runner", "dmr", "openai", "openai_compatible"} or "/engines/" in api_base


def parse_model_json(value: Any) -> tuple[dict[str, Any] | None, str]:
    if isinstance(value, dict):
        return value, ""
    if not isinstance(value, str):
        return None, f"unsupported response type: {type(value).__name__}"

    errors: list[str] = []
    candidates = model_json_candidates(value)
    for candidate in candidates:
        for variant in repair_json_candidates(candidate):
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as exc:
                errors.append(str(exc))
                continue
            if isinstance(parsed, dict):
                return parsed, ""
            return None, f"JSON response was {type(parsed).__name__}, expected object"

    if not candidates:
        return None, "non-json response"
    return None, f"malformed json response: {errors[-1] if errors else 'unknown parse error'}"


def model_json_candidates(text: str) -> list[str]:
    stripped = strip_json_code_fence(text)
    candidates = [stripped] if stripped else []

    balanced = first_balanced_json_object(stripped)
    if balanced and balanced not in candidates:
        candidates.append(balanced)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        loose = stripped[start : end + 1]
        if loose not in candidates:
            candidates.append(loose)
    return candidates


def strip_json_code_fence(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def first_balanced_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def repair_json_candidates(candidate: str) -> list[str]:
    repaired = remove_trailing_json_commas(insert_missing_json_commas(candidate))
    candidates = [candidate]
    if repaired != candidate:
        candidates.append(repaired)
    return candidates


JSON_KEY_PATTERN = r'("(?:(?:\\.)|[^"\\])*"\s*:)'


def insert_missing_json_commas(candidate: str) -> str:
    fixed = re.sub(
        rf'([}}\]"0-9])(\s*\n\s*){JSON_KEY_PATTERN}',
        r"\1,\2\3",
        candidate,
    )
    fixed = re.sub(
        rf'\b(true|false|null)(\s*\n\s*){JSON_KEY_PATTERN}',
        r"\1,\2\3",
        fixed,
    )
    return fixed


def remove_trailing_json_commas(candidate: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", candidate)


def fallback_detection_from_model_text(_text: str, _reason: str) -> dict[str, Any]:
    return normalize_detection(
        {
            "detected": False,
            "detected_target": False,
            "detection_count": 0,
            "detections": [],
            "confidence": 0.0,
            "summary": "No reliable visual detection was produced for this frame.",
            "detection_report": "",
            "activity_description": "",
            "detected_types": [],
            "detected_colors": [],
            "appearance_notes": [],
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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_string(value: Any, limit: int = 500) -> str:
    text = "" if value is None else " ".join(str(value).split())
    return text[:limit]


def normalize_attention_instruction(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return compact_string(", ".join(item for item in (normalize_attention_instruction(item) for item in value) if item))
    if isinstance(value, dict):
        parts = []
        for key in ("target", "label", "detail", "description", "zone", "color", "activity"):
            text = compact_string(value.get(key), limit=120)
            if text:
                parts.append(f"{key}: {text}")
        if parts:
            return compact_string("; ".join(parts))
        try:
            return compact_string(json.dumps(value, sort_keys=True))
        except TypeError:
            return compact_string(value)
    return compact_string(value)


def looks_like_attention_request(text: str) -> bool:
    normalized = text.lower()
    return any(
        phrase in normalized
        for phrase in (
            "pay attention",
            "watch for",
            "focus on",
            "look for",
            "track ",
            "keep an eye",
            "notice if",
            "tell me if",
            "monitor for",
        )
    )


def attention_request_from_inputs(payload: dict[str, Any], message: dict[str, Any]) -> str:
    direct_keys = (
        "attention_instruction",
        "attention_request",
        "attention_targets",
        "watch_for",
        "watch_details",
        "pay_attention_to",
        "focus_on",
        "look_for",
        "track_details",
    )
    message_payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    for container in (payload, message, message_payload):
        if not isinstance(container, dict):
            continue
        for key in direct_keys:
            instruction = normalize_attention_instruction(container.get(key))
            if instruction:
                return instruction

        for key in ("user_message", "chat_message", "message", "prompt"):
            instruction = normalize_attention_instruction(container.get(key))
            if instruction and looks_like_attention_request(instruction):
                return instruction
    return ""


def apply_attention_request(
    state: dict[str, Any],
    payload: dict[str, Any],
    message: dict[str, Any],
    camera_id: str,
) -> dict[str, Any] | None:
    instruction = attention_request_from_inputs(payload, message)
    if not instruction:
        return None

    previous = normalize_attention_instruction(state.get("attention_instruction"))
    state["attention_instruction"] = instruction
    state["attention_targets"] = [instruction]
    state["last_attention_update"] = {
        "camera_id": camera_id,
        "instruction": instruction,
        "updated_at_wall_ts": time.time(),
    }
    if previous == instruction:
        return None

    return {
        "type": "video_watch_attention_updated",
        "payload": {
            "camera_id": camera_id,
            "attention_instruction": instruction,
            "attention_targets": [instruction],
            "summary": f"Operator attention request updated: {instruction}",
        },
    }


def detection_prompt(camera_id: str, attention_instruction: str | None = None) -> str:
    target_description = os.environ.get(
        "VISUAL_DETECTION_TARGETS",
        "notable people, equipment, objects, hazards, access activity, workflow activity, or other user-defined subjects",
    )
    attention_text = normalize_attention_instruction(attention_instruction)
    attention_clause = (
        f" The operator also asked you to pay particular attention to: {attention_text}."
        if attention_text
        else ""
    )
    return os.environ.get(
        "VISUAL_DETECTION_PROMPT",
        (
            "You are monitoring a 24/7 video camera. Inspect the image and decide whether any configured "
            f"visual targets are present or active. Targets to watch for: {target_description}. Count only real "
            "visible subjects or activity; ignore shadows, reflections, signage text, static background clutter, "
            f"and uncertain guesses unless they are directly relevant to the configured targets.{attention_clause} "
            "For every detection, "
            "report the observable label, category, visible color if useful, position in the scene, and activity. "
            "Return only JSON with keys: detected boolean, detected_target boolean, detection_count integer, "
            "detections array of objects with label, category, color, position, activity, and confidence, confidence "
            "number from 0 to 1, summary short string, detection_report string, activity_description string, "
            "detected_types array of strings, detected_colors array of strings, appearance_notes array of strings, "
            f"risk_level one of low/medium/high, and visible_subjects array. Camera id: {camera_id}."
        ),
    )


PERSON_TERMS = ("person", "people", "human", "worker", "visitor", "operator", "pedestrian")


def person_like_count(detection: dict[str, Any]) -> int:
    detections = detection.get("detections") if isinstance(detection.get("detections"), list) else []
    detection_people = 0
    for item in detections:
        if not isinstance(item, dict):
            continue
        text = " ".join(
            compact_string(item.get(key), limit=100).lower()
            for key in ("label", "category", "activity")
        )
        if any(term in text for term in PERSON_TERMS):
            detection_people += 1

    visible_subjects = detection.get("visible_subjects") if isinstance(detection.get("visible_subjects"), list) else []
    subject_people = sum(
        1
        for subject in visible_subjects
        if any(term in compact_string(subject, limit=100).lower() for term in PERSON_TERMS)
    )

    count = safe_int(detection.get("detection_count"), 0)
    text = " ".join(
        compact_string(detection.get(key), limit=500).lower()
        for key in ("summary", "detection_report", "activity_description")
    )
    inferred_people = count if count >= 2 and any(term in text for term in PERSON_TERMS) else 0
    return max(detection_people, subject_people, inferred_people)


def observation_from_detection(detection_payload: dict[str, Any]) -> dict[str, Any]:
    detected = bool(detection_payload.get("detected_target"))
    summary = compact_string(detection_payload.get("summary"), limit=500)
    report = compact_string(detection_payload.get("detection_report"), limit=900)
    activity = compact_string(detection_payload.get("activity_description"), limit=700)
    fallback = "No configured targets were observed in the monitored scene."
    return {
        "frame_seq": detection_payload.get("frame_seq"),
        "camera_id": detection_payload.get("camera_id"),
        "video_position_seconds": detection_payload.get("video_position_seconds"),
        "source_uri": detection_payload.get("source_uri"),
        "stream_id": detection_payload.get("stream_id"),
        "detected_target": detected,
        "detection_count": safe_int(detection_payload.get("detection_count"), 0),
        "confidence": safe_confidence(detection_payload.get("confidence")),
        "risk_level": compact_string(detection_payload.get("risk_level"), limit=40) or "low",
        "summary": summary or fallback,
        "detection_report": report,
        "activity_description": activity,
        "visible_subjects": detection_payload.get("visible_subjects") if isinstance(detection_payload.get("visible_subjects"), list) else [],
        "detections": detection_payload.get("detections") if isinstance(detection_payload.get("detections"), list) else [],
        "person_like_count": person_like_count(detection_payload),
        "attention_instruction": compact_string(detection_payload.get("attention_instruction"), limit=500),
    }


def what_happened_summary(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "No video frames have been analyzed yet."

    last = observations[-1]
    frame = last.get("frame_seq", "unknown")
    camera_id = last.get("camera_id") or "the monitored camera"
    if last.get("detected_target"):
        report = compact_string(last.get("detection_report"), limit=500) or compact_string(last.get("summary"), limit=500)
        activity = compact_string(last.get("activity_description"), limit=300)
        details = f" Activity: {activity}" if activity else ""
        return f"Most recently on frame {frame} from {camera_id}, {report}{details}"

    previous_notable = next((item for item in reversed(observations[:-1]) if item.get("detected_target")), None)
    if previous_notable:
        notable_report = (
            compact_string(previous_notable.get("detection_report"), limit=400)
            or compact_string(previous_notable.get("summary"), limit=400)
        )
        return (
            f"Most recently on frame {frame} from {camera_id}, no configured targets were observed. "
            f"The last notable observation was frame {previous_notable.get('frame_seq')}: {notable_report}"
        ).strip()

    return (
        f"Most recently on frame {frame} from {camera_id}, no configured targets were observed. "
        f"{compact_string(last.get('summary'), limit=300)}"
    ).strip()


def update_conversation_context(state: dict[str, Any], detection_payload: dict[str, Any]) -> dict[str, Any]:
    observation = observation_from_detection(detection_payload)
    recent = state.get("recent_observations")
    if not isinstance(recent, list):
        recent = []
    recent = [item for item in recent if isinstance(item, dict)]
    recent.append(observation)
    recent = recent[-10:]
    state["recent_observations"] = recent
    state["last_observation"] = observation
    state["conversation_context"] = {
        "what_happened": what_happened_summary(recent),
        "last_observation": observation,
        "recent_observations": recent[-5:],
        "attention_instruction": compact_string(state.get("attention_instruction"), limit=500),
    }
    return observation


def frame_observed_event(observation: dict[str, Any], conversation_summary: str = "") -> dict[str, Any]:
    return {
        "type": "video_watch_frame_observed",
        "payload": {
            "camera_id": observation.get("camera_id"),
            "frame_seq": observation.get("frame_seq"),
            "video_position_seconds": observation.get("video_position_seconds"),
            "stream_id": observation.get("stream_id"),
            "detected_target": observation.get("detected_target"),
            "detection_count": observation.get("detection_count"),
            "confidence": observation.get("confidence"),
            "risk_level": observation.get("risk_level"),
            "summary": observation.get("summary"),
            "detection_report": observation.get("detection_report"),
            "activity_description": observation.get("activity_description"),
            "visible_subjects": observation.get("visible_subjects"),
            "attention_instruction": observation.get("attention_instruction"),
            "conversation_summary": conversation_summary or what_happened_summary([observation]),
        },
    }


def human_notice_cooldown_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("HUMAN_NOTICE_COOLDOWN_SECONDS", "30")))
    except ValueError:
        return 30.0


def scene_change_reason(detection_payload: dict[str, Any], previous_observation: dict[str, Any]) -> str:
    if not detection_payload.get("detected_target"):
        return ""

    current_count = safe_int(detection_payload.get("detection_count"), 0)
    previous_count = safe_int(previous_observation.get("detection_count"), 0)
    current_people = person_like_count(detection_payload)
    previous_people = safe_int(previous_observation.get("person_like_count"), 0)
    risk_level = compact_string(detection_payload.get("risk_level"), limit=40).lower()
    previous_risk = compact_string(previous_observation.get("risk_level"), limit=40).lower()

    if current_people >= 2 and previous_people < 2:
        return f"{current_people} people are now visible in the monitored scene."
    if current_count >= 2 and previous_count == 0:
        return f"{current_count} configured targets appeared in the monitored scene."
    if current_count - previous_count >= 2:
        return f"The scene changed from {previous_count} to {current_count} configured targets."
    if risk_level == "high" and previous_risk != "high":
        return "The scene is now marked high risk."
    return ""


def scene_change_signature(detection_payload: dict[str, Any]) -> str:
    labels = []
    detections = detection_payload.get("detections") if isinstance(detection_payload.get("detections"), list) else []
    for item in detections:
        if isinstance(item, dict):
            label = compact_string(item.get("label"), limit=80)
            position = compact_string(item.get("position"), limit=80)
            labels.append(f"{label}@{position}".strip("@"))
    if not labels:
        labels = [compact_string(item, limit=80) for item in detection_payload.get("visible_subjects", [])]
    return "|".join(sorted(item for item in labels if item))[:300] or compact_string(detection_payload.get("summary"), limit=300)


def maybe_build_big_change_notice(
    detection_payload: dict[str, Any],
    state: dict[str, Any],
    previous_observation: dict[str, Any],
) -> dict[str, Any] | None:
    reason = scene_change_reason(detection_payload, previous_observation)
    if not reason:
        return None

    signature = f"video_big_change:{detection_payload.get('camera_id')}:{scene_change_signature(detection_payload)}"
    now = time.time()
    last_signature = state.get("last_human_notice_signature")
    last_notice_ts = float(state.get("last_human_notice_wall_ts", 0.0) or 0.0)
    if signature == last_signature and now - last_notice_ts < human_notice_cooldown_seconds():
        return None

    state["last_human_notice_signature"] = signature
    state["last_human_notice_wall_ts"] = now
    camera_id = compact_string(detection_payload.get("camera_id"), limit=80) or "video-watch"
    frame_seq = detection_payload.get("frame_seq")
    summary = compact_string(detection_payload.get("detection_report"), limit=600) or compact_string(detection_payload.get("summary"), limit=500)
    message = compact_string(f"{reason} {summary}", limit=900)
    notice_id = f"video-watch-big-change-{camera_id}-{frame_seq}"
    return {
        "type": "human_notice",
        "channel": "human",
        "payload": {
            "notice_id": notice_id,
            "kind": "video_big_change",
            "level": "attention",
            "title": "Big change in video",
            "message": message,
            "detail": summary,
            "camera_id": camera_id,
            "frame_seq": frame_seq,
            "detection_count": detection_payload.get("detection_count"),
            "visible_subjects": detection_payload.get("visible_subjects"),
            "chat_delivery": "otterdesk_worker_chat",
            "requires_ack": True,
        },
    }


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
    start_agent_beacon_thread("Video detector is analyzing a frame")
    message = load_json_env("MN_MESSAGE_FILE")
    payload = load_json_env("MN_INPUT_FILE")
    context = load_json_env("MN_CONTEXT_FILE")
    state = context.get("agent_state") or initial_state()
    if not isinstance(state, dict):
        state = initial_state()

    frame_seq = int(payload.get("tick_seq") or state.get("frames_seen", 0) + 1)
    camera_id = payload.get("camera_id") or os.environ.get("CAMERA_ID", "video-watch")
    source_uri = os.environ.get("VIDEO_SOURCE_URI", DEFAULT_VIDEO_SOURCE_URI)
    sample_seconds = float(os.environ.get("FRAME_SAMPLE_SECONDS", "10.0"))
    max_width = int(os.environ.get("FRAME_JPEG_MAX_WIDTH", "896"))

    events: list[dict[str, Any]] = []
    stream = message.get("stream") or {}

    try:
        attention_event = apply_attention_request(state, payload, message, camera_id)
        if attention_event:
            events.append(attention_event)
        attention_instruction = normalize_attention_instruction(state.get("attention_instruction"))
        position = float(state.get("video_position_seconds", 0.0))
        if os.environ.get("MOCK_VLM_DETECTION", "false").strip().lower() in {"1", "true", "yes", "on"}:
            detection = mock_detection(frame_seq)
        else:
            frame, _content_type = extract_frame(source_uri, position, max_width)
            detection = call_ollama(frame, detection_prompt(camera_id, attention_instruction))

        detection_payload = {
            **detection,
            "camera_id": camera_id,
            "frame_seq": frame_seq,
            "video_position_seconds": round(position, 3),
            "source_uri": source_uri,
            "stream_id": stream.get("stream_id"),
            "attention_instruction": attention_instruction,
        }
        previous_observation = state.get("last_observation") if isinstance(state.get("last_observation"), dict) else {}
        observation = update_conversation_context(state, detection_payload)
        conversation_context = state.get("conversation_context") if isinstance(state.get("conversation_context"), dict) else {}
        conversation_summary = conversation_context.get("what_happened", "")
        events.append(frame_observed_event(observation, conversation_summary))
        if detection["detected_target"]:
            state["detections"] = int(state.get("detections", 0)) + 1
            state["last_detection"] = detection_payload
            state["last_detection_report"] = detection_payload.get("detection_report")
            events.append({"type": "video_watch_detection", "payload": detection_payload})

        big_change_notice = maybe_build_big_change_notice(detection_payload, state, previous_observation)
        if big_change_notice:
            events.append(big_change_notice)

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
