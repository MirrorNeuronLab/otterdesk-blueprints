from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .utils import read_json_file


def resolve_input_overrides(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    section = config.get("inputs") or {}
    adapter = str(section.get("adapter") or "mock")
    if adapter == "mock":
        payload = section.get("payload") or {}
    elif adapter == "json":
        payload = section.get("payload") or {}
    elif adapter == "file":
        path = section.get("path")
        if not path:
            raise ValueError("file input adapter requires inputs.path")
        payload = read_json_file(Path(path))
    elif adapter == "env_json":
        env_var = section.get("env_var") or "MN_BLUEPRINT_INPUT_JSON"
        raw = os.environ.get(env_var, "{}")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"{env_var} must decode to a JSON object")
    else:
        raise ValueError(f"unknown input adapter {adapter!r}")

    if not isinstance(payload, dict):
        raise ValueError("input adapter payload must be a JSON object")

    source = {
        "adapter": adapter,
        "path": section.get("path"),
        "description": section.get("description"),
        "real_ready": adapter != "mock",
    }
    return dict(payload), source
