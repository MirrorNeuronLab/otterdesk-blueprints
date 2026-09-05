#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


START_MESSAGE = "cctv_operator_start"
STEERING_MESSAGE = "cctv_operator_steer"


def load_json_env(name: str) -> dict[str, Any]:
    path = str(os.environ.get(name) or "").strip()
    if not path or not Path(path).is_file():
        return {}
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def routed_input(
    payload: dict[str, Any], message: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    envelope = (
        message.get("envelope")
        if isinstance(message.get("envelope"), dict)
        else {}
    )
    declared_type = str(
        payload.get("type")
        or message.get("type")
        or envelope.get("type")
        or START_MESSAGE
    ).strip()
    message_type = (
        STEERING_MESSAGE if declared_type == STEERING_MESSAGE else START_MESSAGE
    )
    nested_payload = payload.get("payload")
    body = nested_payload if isinstance(nested_payload, dict) else payload
    return message_type, body


def validate_start() -> tuple[bool, str]:
    validator = Path(__file__).with_name("validate_video_source.py")
    completed = subprocess.run(
        [sys.executable, str(validator)],
        capture_output=True,
        check=False,
        env=os.environ.copy(),
        text=True,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output


def main() -> int:
    payload = load_json_env("MN_INPUT_FILE")
    message = load_json_env("MN_MESSAGE_FILE")
    message_type, body = routed_input(payload, message)

    validation_summary = "Steering command accepted."
    if message_type == START_MESSAGE:
        valid, validation_summary = validate_start()
        if not valid:
            print(validation_summary, file=sys.stderr)
            return 1

    print(
        json.dumps(
            {
                "complete_step": {
                    "stream_session": {
                        "status": "ready",
                        "stream_id": str(body.get("stream_id") or "cctv_operator"),
                    },
                    "validation": validation_summary,
                },
                "emit_messages": [
                    {
                        "body": body,
                        "type": message_type,
                    }
                ],
                "events": [
                    {
                        "payload": {
                            "message_type": message_type,
                            "status": "ready",
                        },
                        "type": "video_monitor_start",
                    }
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
