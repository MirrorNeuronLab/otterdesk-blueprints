from __future__ import annotations

import time
import uuid
from typing import Any, Mapping


MAX_INSTRUCTION_CHARS = 500


def initial_monitoring_state() -> dict[str, Any]:
    return {
        "instruction": "",
        "instruction_revision": 0,
        "last_command_id": "",
        "updated_at": None,
    }


def normalize_instruction(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())[:MAX_INSTRUCTION_CHARS]


def is_steering_command(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in ("instruction", "clear", "analyze_now", "command_id"))


def apply_steering_command(
    state: Mapping[str, Any] | None,
    payload: Mapping[str, Any],
    *,
    now: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = {**initial_monitoring_state(), **dict(state or {})}
    clear = bool(payload.get("clear"))
    instruction = "" if clear else normalize_instruction(payload.get("instruction"))
    if not clear and not instruction:
        raise ValueError("steering instruction must not be empty unless clear=true")

    revision = int(current.get("instruction_revision") or 0) + 1
    command_id = normalize_instruction(payload.get("command_id")) or uuid.uuid4().hex
    updated_at = float(now if now is not None else time.time())
    current.update(
        {
            "instruction": instruction,
            "instruction_revision": revision,
            "last_command_id": command_id,
            "updated_at": updated_at,
        }
    )
    event = {
        "type": "cctv_operator_attention_updated",
        "payload": {
            "command_id": command_id,
            "instruction": instruction,
            "instruction_revision": revision,
            "cleared": clear,
            "analyze_now": bool(payload.get("analyze_now", True)),
            "updated_at": updated_at,
            "summary": (
                "The current monitoring instruction was cleared."
                if clear
                else f"Monitoring instruction updated: {instruction}"
            ),
        },
    }
    return current, event
