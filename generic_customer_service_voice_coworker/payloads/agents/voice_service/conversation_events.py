"""JSONL event helpers for the voice service."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_dir() -> Path:
    return Path(os.getenv("MN_RUN_DIR") or os.getenv("CUSTOMER_SERVICE_RUN_DIR") or ".").expanduser()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def emit_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    record = {
        "type": event_type,
        "ts": utc_now(),
        "payload": payload or {},
        "source": "customer_service_voice_service",
    }
    append_jsonl(run_dir() / "events.jsonl", record)


def emit_log(message: str, *, level: str = "INFO", **extra: Any) -> None:
    record = {"ts": utc_now(), "level": level, "message": message, **extra}
    append_jsonl(run_dir() / "logs.jsonl", record)


def append_conversation(role: str, text: str, **extra: Any) -> None:
    record = {"ts": utc_now(), "role": role, "text": text, **extra}
    append_jsonl(run_dir() / "conversation.jsonl", record)

