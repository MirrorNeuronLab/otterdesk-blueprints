#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
import signal
import threading
import urllib.parse
from collections import deque
from pathlib import Path
from typing import Any, Callable

import grpc
from mn_live_video_analysis_skill import (
    redact_source_urls,
)
from mn_sdk import Client
from mn_web_ui_skill import (
    ActionResponse,
    JsonRenderApplication,
    JsonRenderServer,
    StaticMount,
    write_service_artifacts,
)


WEB_UI_NODE_ID = "cctv_web_ui"
WEB_UI_SERVICE_NAME = "cctv-operator-web-ui"
STEERING_INPUT_ID = "steer_monitoring"
STEERING_ACTION = "steer-monitoring"
SendRunInput = Callable[[str, str, dict[str, Any], str], dict[str, Any]]


def load_config() -> dict[str, Any]:
    try:
        decoded = json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}"))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def configured_run_dir() -> Path:
    explicit = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    runs_root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    run_id = configured_run_id()
    return (
        Path(runs_root).expanduser() / run_id
        if runs_root
        else Path.cwd() / "runs" / run_id
    )


def configured_run_id() -> str:
    return str(
        os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run"
    ).strip()


def validate_steering_payload(payload: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(payload) - {"instruction", "analyze_now", "clear"})
    if unknown:
        raise ValueError(f"unknown steering fields: {', '.join(unknown)}")
    clear = payload.get("clear", False)
    analyze_now = payload.get("analyze_now", True)
    if type(clear) is not bool:
        raise ValueError("clear must be a boolean")
    if type(analyze_now) is not bool:
        raise ValueError("analyze_now must be a boolean")
    instruction = payload.get("instruction", "")
    if not isinstance(instruction, str):
        raise ValueError("instruction must be a string")
    instruction = " ".join(instruction.split()).strip()
    if len(instruction) > 500:
        raise ValueError("instruction must not exceed 500 characters")
    if not clear and not instruction:
        raise ValueError("instruction is required unless clear is true")
    return {
        "instruction": "" if clear else instruction,
        "analyze_now": analyze_now,
        "clear": clear,
    }


def validate_preview_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if len(url) > 2048:
        raise ValueError("web_ui.preview.url must not exceed 2048 characters")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "web_ui.preview.url must be an absolute HTTP(S) URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(
            "web_ui.preview.url must not contain embedded credentials"
        )
    return url


def preview_config(config: dict[str, Any]) -> tuple[str, str, str]:
    web_ui = config.get("web_ui")
    web_ui = web_ui if isinstance(web_ui, dict) else {}
    preview = web_ui.get("preview")
    preview = preview if isinstance(preview, dict) else {}
    if not bool(preview.get("enabled", True)):
        return "", "disabled", ""
    url = validate_preview_url(preview.get("url"))
    if not url:
        return (
            "",
            "unavailable",
            (
                "Live preview URL is not configured; sparse analysis "
                "remains active."
            ),
        )
    return url, "external", ""


def build_ui_spec(preview_url: str = "") -> dict[str, Any]:
    preview_element = (
        {
            "type": "Video",
            "props": {
                "source": preview_url,
                "label": (
                    "Preview is observational. Analysis uses sparse "
                    "selected frame batches."
                ),
            },
            "children": [],
        }
        if preview_url
        else {
            "type": "Text",
            "props": {
                "text": (
                    "No browser-safe preview URL is configured. "
                    "Video analysis continues independently."
                )
            },
            "children": [],
        }
    )
    return {
        "root": "app",
        "elements": {
            "app": {
                "type": "App",
                "props": {
                    "title": "CCTV Operator",
                    "subtitle": (
                        "Smooth preview and the bounded evidence actually "
                        "selected for multimodal analysis."
                    ),
                },
                "children": ["layout"],
            },
            "layout": {
                "type": "Grid",
                "props": {},
                "children": [
                    "preview",
                    "controls",
                    "latest",
                    "events",
                ],
            },
            "preview": {
                "type": "Card",
                "props": {"title": "Live source preview", "span": 8},
                "children": ["preview-video"],
            },
            "preview-video": preview_element,
            "controls": {
                "type": "Card",
                "props": {"title": "Steer monitoring", "span": 4},
                "children": ["status", "update-watch", "clear-watch"],
            },
            "status": {
                "type": "LiveStatus",
                "props": {"endpoint": "/ui/state", "refreshMs": 1000},
                "children": [],
            },
            "update-watch": {
                "type": "ActionForm",
                "props": {
                    "action": STEERING_ACTION,
                    "label": "Update watch target",
                    "fields": [
                        {
                            "name": "instruction",
                            "label": "What should the AI monitor?",
                            "type": "textarea",
                            "required": True,
                            "max_length": 500,
                            "rows": 4,
                            "placeholder": (
                                "Watch for a red backpack near the left doorway."
                            ),
                        },
                        {
                            "name": "analyze_now",
                            "label": "Analyze now",
                            "type": "boolean",
                            "default": True,
                        },
                    ],
                },
                "children": [],
            },
            "clear-watch": {
                "type": "ActionForm",
                "props": {
                    "action": STEERING_ACTION,
                    "label": "Clear watch target",
                    "fields": [],
                    "payload": {"clear": True, "analyze_now": True},
                },
                "children": [],
            },
            "latest": {
                "type": "Card",
                "props": {"title": "Latest frame analyzed by AI", "span": 6},
                "children": ["latest-image"],
            },
            "latest-image": {
                "type": "ArtifactImage",
                "props": {
                    "source": "/artifacts/latest_analyzed_frame.jpg",
                    "alt": "Latest selected CCTV frame analyzed by the model",
                    "refreshMs": 1500,
                },
                "children": [],
            },
            "events": {
                "type": "Card",
                "props": {"title": "Sampling and observation events", "span": 6},
                "children": ["event-feed"],
            },
            "event-feed": {
                "type": "EventFeed",
                "props": {
                    "endpoint": "/ui/state",
                    "refreshMs": 1000,
                    "limit": 30,
                },
                "children": [],
            },
        },
    }


class CCTVWebUIService:
    def __init__(
        self,
        *,
        run_id: str,
        run_dir: Path,
        config: dict[str, Any],
        send_run_input: SendRunInput,
    ) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.config = config
        self.send_run_input = send_run_input
        (
            self.preview_url,
            self.preview_status,
            self.preview_warning,
        ) = preview_config(config)
        self.application = JsonRenderApplication(
            title="CCTV Operator",
            spec=build_ui_spec(self.preview_url),
            state_provider=self.ui_state,
            actions={STEERING_ACTION: self.steer_monitoring},
            static_mounts=(
                StaticMount(
                    "/artifacts",
                    run_dir,
                    allowed_paths=frozenset(
                        {
                            "latest_analyzed_frame.jpg",
                            "latest_analyzed_frame.json",
                        }
                    ),
                ),
            ),
        )

    def steer_monitoring(
        self,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> ActionResponse:
        normalized = validate_steering_payload(payload)
        try:
            response = self.send_run_input(
                self.run_id,
                STEERING_INPUT_ID,
                normalized,
                idempotency_key,
            )
        except grpc.RpcError as exc:
            code = exc.code()
            status = {
                grpc.StatusCode.NOT_FOUND: 404,
                grpc.StatusCode.FAILED_PRECONDITION: 409,
                grpc.StatusCode.INVALID_ARGUMENT: 422,
                grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
            }.get(code, 502)
            headers = {"Retry-After": "1"} if status == 429 else {}
            return ActionResponse(
                {
                    "error": str(
                        exc.details() or "monitoring instruction was rejected"
                    )
                },
                status_code=status,
                headers=headers,
            )
        action = "cleared" if normalized["clear"] else "updated"
        suffix = (
            " and immediate analysis was queued."
            if normalized["analyze_now"]
            else "."
        )
        return ActionResponse(
            {
                "message": f"Monitoring instruction {action}{suffix}",
                "status": response.get("status", "accepted"),
                "command_id": response.get("command_id") or idempotency_key,
            },
            status_code=202,
        )

    def ui_state(self) -> dict[str, Any]:
        events = read_event_tail(self.run_dir / "events.jsonl", limit=80)
        latest_attention = _latest_event(
            events, "cctv_operator_attention_updated"
        )
        latest_batch = _latest_event(events, "cctv_operator_frame_batch_ready")
        attention_payload = _event_payload(latest_attention)
        monitoring_state = read_monitoring_state(
            self.run_dir / "monitoring_state.json"
        )
        if int(monitoring_state.get("instruction_revision") or 0) >= int(
            attention_payload.get("instruction_revision") or 0
        ):
            attention_payload = monitoring_state
        batch_payload = _event_payload(latest_batch)
        return {
            "metrics": {
                "run": self.run_id,
                "preview": self.preview_status,
                "instruction revision": attention_payload.get(
                    "instruction_revision", 0
                ),
                "watch target": attention_payload.get("instruction")
                or "Default visual targets",
                "latest trigger": batch_payload.get("trigger", "waiting"),
                "selected frames": batch_payload.get("selected_count", 0),
            },
            "warning": self.preview_warning,
            "events": [_public_event(event) for event in events[-50:]],
        }


def read_event_tail(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.is_file() or limit < 1:
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    sanitized = json.loads(redact_source_urls(json.dumps(value)))
                    rows.append(sanitized)
    except OSError:
        return []
    return list(rows)


def read_monitoring_state(path: Path) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    instruction = decoded.get("instruction")
    revision = decoded.get("instruction_revision")
    if not isinstance(instruction, str):
        return {}
    try:
        normalized_revision = max(int(revision or 0), 0)
    except (TypeError, ValueError):
        return {}
    return {
        "instruction": " ".join(instruction.split())[:500],
        "instruction_revision": normalized_revision,
        "updated_at": decoded.get("updated_at"),
        "command_id": str(decoded.get("last_command_id") or "")[:500],
    }


def _latest_event(
    events: list[dict[str, Any]], event_type: str
) -> dict[str, Any]:
    return next(
        (
            event
            for event in reversed(events)
            if event.get("type") == event_type
        ),
        {},
    )


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = _event_payload(event)
    return {
        "type": str(event.get("type") or "event"),
        "timestamp": str(event.get("timestamp") or event.get("ts") or ""),
        "summary": str(
            payload.get("summary")
            or payload.get("reason")
            or payload.get("error")
            or ""
        )[:500],
    }


def core_send_run_input(
    run_id: str,
    input_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    raw = Client().send_run_input(
        run_id,
        input_id,
        payload,
        idempotency_key=idempotency_key,
    )
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "accepted"}
    return decoded if isinstance(decoded, dict) else {"status": "accepted"}


def public_service_url(
    host: str,
    port: int,
    configured_url: str = "",
) -> str:
    explicit = str(configured_url or "").strip().rstrip("/")
    if explicit:
        return explicit
    display_host = (
        "127.0.0.1" if host in {"0.0.0.0", "::", "[::]"} else host
    )
    return f"http://{display_host}:{port}"


def main() -> int:
    config = load_config()
    run_id = configured_run_id()
    run_dir = configured_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    web_ui = config.get("web_ui")
    web_ui = web_ui if isinstance(web_ui, dict) else {}
    service_config = web_ui.get("service")
    service_config = service_config if isinstance(service_config, dict) else {}
    host = str(service_config.get("host") or "127.0.0.1")
    port = int(service_config.get("port") or 61000)
    public_url = public_service_url(
        host,
        port,
        str(service_config.get("public_url") or ""),
    )

    service = CCTVWebUIService(
        run_id=run_id,
        run_dir=run_dir,
        config=config,
        send_run_input=core_send_run_input,
    )
    server = JsonRenderServer(service.application, host=host, port=port)
    write_service_artifacts(
        run_dir,
        run_id=run_id,
        title="CCTV Operator",
        url=public_url,
        spec=service.application.spec,
        service_name=WEB_UI_SERVICE_NAME,
        node_id=WEB_UI_NODE_ID,
        metadata={
            "listen_host": host,
            "listen_port": port,
            "preview_url": service.preview_url,
            "latest_analyzed_frame_url": (
                f"{public_url}/artifacts/latest_analyzed_frame.jpg"
            ),
            "steering_action": f"{public_url}/actions/{STEERING_ACTION}",
        },
    )

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.stop, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
