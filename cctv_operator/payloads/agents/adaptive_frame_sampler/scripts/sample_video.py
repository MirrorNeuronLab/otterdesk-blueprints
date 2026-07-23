#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
for ancestor in (SCRIPT_DIR, *SCRIPT_DIR.parents):
    if (ancestor / "domain").is_dir() and str(ancestor) not in sys.path:
        sys.path.insert(0, str(ancestor))
        break


def _bootstrap_runtime() -> None:
    for parent in Path(__file__).resolve().parents:
        helper = parent / "otterdesk_blueprint_env.py"
        if helper.exists():
            spec = importlib.util.spec_from_file_location(
                "otterdesk_blueprint_env", helper
            )
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.bootstrap_blueprint_runtime(
                __file__,
                packages=(
                    "mirrorneuron-blueprint-support-skill",
                    "mirrorneuron-live-video-analysis-skill",
                ),
            )
            return


_bootstrap_runtime()

from domain.monitoring import (
    apply_steering_command,
    initial_monitoring_state,
    is_steering_command,
)
from mn_blueprint_support import start_agent_beacon_thread
from mn_live_video_analysis_skill import (
    AdaptiveStreamSampler,
    SamplingPolicy,
    initial_sampling_state,
)


_EVENT_NAMES = {
    "scene_change_detected": "cctv_operator_scene_change_detected",
    "queue_lag": "cctv_operator_queue_lag",
    "sampling_skipped": "cctv_operator_sample_skipped",
    "burst_started": "cctv_operator_burst_started",
    "burst_completed": "cctv_operator_burst_completed",
    "batch_ready": "cctv_operator_frame_batch_ready",
}


def load_json_env(name: str) -> dict[str, Any]:
    value = os.environ.get(name)
    if not value or not Path(value).is_file():
        return {}
    try:
        decoded = json.loads(Path(value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def load_config() -> dict[str, Any]:
    try:
        decoded = json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}"))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def run_dir() -> Path:
    explicit = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    runs_root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    run_id = str(
        os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run"
    ).strip()
    return (
        Path(runs_root).expanduser() / run_id
        if runs_root
        else Path.cwd() / "run_artifacts"
    )


def initial_state() -> dict[str, Any]:
    return {
        **initial_sampling_state(),
        "monitoring": initial_monitoring_state(),
    }


def live_input_command_id(message: dict[str, Any]) -> str:
    envelope = (
        message.get("envelope")
        if isinstance(message.get("envelope"), dict)
        else {}
    )
    for candidate in (message, envelope):
        headers = candidate.get("headers")
        if isinstance(headers, dict):
            value = str(
                headers.get("mn.idempotency_key")
                or headers.get("mn.live_input_command_id")
                or ""
            ).strip()
            if value:
                return value
    return str(
        envelope.get("message_id") or message.get("message_id") or ""
    ).strip()


def _event(value: dict[str, Any]) -> dict[str, Any]:
    kind = str(value.get("kind") or "")
    payload = value.get("payload")
    return {
        "type": _EVENT_NAMES.get(kind, f"cctv_operator_{kind}"),
        "payload": payload if isinstance(payload, dict) else {},
    }


def main() -> int:
    invocation_started = time.monotonic()
    start_agent_beacon_thread(
        "CCTV adaptive sampler is inspecting the proxy stream"
    )
    config = load_config()
    policy = SamplingPolicy.from_mapping(config.get("sampling"))
    payload = load_json_env("MN_INPUT_FILE")
    message = load_json_env("MN_MESSAGE_FILE")
    context = load_json_env("MN_CONTEXT_FILE")
    prior_state = context.get("agent_state")
    state = {
        **initial_state(),
        **(prior_state if isinstance(prior_state, dict) else {}),
    }
    monitoring = state.get("monitoring")
    monitoring = {
        **initial_monitoring_state(),
        **(monitoring if isinstance(monitoring, dict) else {}),
    }
    events: list[dict[str, Any]] = []
    emit_messages: list[dict[str, Any]] = []
    steering_message = is_steering_command(payload)
    invocation_id = live_input_command_id(message)
    analyze_now = False

    if steering_message:
        command_id = invocation_id
        if command_id:
            payload = {**payload, "command_id": command_id}
        try:
            monitoring, attention_event = apply_steering_command(
                monitoring, payload, now=time.time()
            )
            events.append(attention_event)
            analyze_now = bool(
                attention_event["payload"]["analyze_now"]
            )
        except ValueError as exc:
            events.append(
                {
                    "type": "cctv_operator_sample_skipped",
                    "payload": {
                        "reason": "invalid_steering",
                        "error": str(exc),
                        "command_id": payload.get("command_id"),
                    },
                }
            )
    state["monitoring"] = monitoring

    try:
        result = AdaptiveStreamSampler(
            run_dir=run_dir(),
            policy=policy,
            batch_schema="otterdesk.cctv_operator.frame_batch.v2",
        ).sample(
            config,
            state,
            force_analysis=analyze_now,
            instruction=str(monitoring.get("instruction") or ""),
            instruction_revision=int(
                monitoring.get("instruction_revision") or 0
            ),
            command_id=str(monitoring.get("last_command_id") or "") or None,
            idempotency_key=invocation_id or None,
            batch_metadata={
                "camera_id": payload.get("camera_id") or "cctv"
            },
        )
        state = result.state
        state["monitoring"] = monitoring
        events.extend(_event(event) for event in result.events)
        if result.batch:
            batch_ref = str(result.batch["frame_batch_ref"])
            emit_messages.append(
                {
                    "type": "cctv_operator_frame_batch_ready",
                    "body": result.batch,
                    "artifacts": [
                        {"path": batch_ref, "type": "frame_batch"}
                    ],
                }
            )
    except Exception as exc:
        state["last_error"] = str(exc)[:800]
        events.append(
            {
                "type": "cctv_operator_frame_analysis_failed",
                "payload": {
                    "stage": "adaptive_sampling",
                    "error": state["last_error"],
                },
            }
        )

    if not steering_message:
        interval = 1.0 / max(policy.proxy_fps, 0.1)
        remaining = interval - (time.monotonic() - invocation_started)
        if remaining > 0:
            time.sleep(remaining)
        emit_messages.append(
            {
                "type": "cctv_operator_sample_due",
                "body": {"scheduled_at": time.time()},
            }
        )

    print(
        json.dumps(
            {
                "next_state": state,
                "events": events,
                "emit_messages": emit_messages,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
