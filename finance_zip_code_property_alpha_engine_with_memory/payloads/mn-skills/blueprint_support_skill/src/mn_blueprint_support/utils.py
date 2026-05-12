from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_run_id(blueprint_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:10]
    return f"{slug(blueprint_id)}-{timestamp}-{suffix}"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def read_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.expanduser().read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")[:80]


def human_label(blueprint_id: str) -> str:
    for prefix in ("general_", "business_", "finance_", "science_"):
        if blueprint_id.startswith(prefix):
            blueprint_id = blueprint_id[len(prefix) :]
            break
    return blueprint_id.replace("_", " ").title()


_read_json_file = read_json_file
_slug = slug
_human_label = human_label
