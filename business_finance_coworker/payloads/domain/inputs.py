from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .common import BUSINESS_GOAL, DEFAULT_BUSINESS_NAME, DEFAULT_GOAL_ID


def normalized_inputs(context: dict[str, Any]) -> dict[str, Any]:
    config_payload = ((context.get("config") or {}).get("inputs") or {}).get("payload") or {}
    payload = {**config_payload, **(context.get("payload") or {}), **(context.get("inputs") or {})}
    payload.setdefault("business_name", DEFAULT_BUSINESS_NAME)
    payload.setdefault("business_goal", BUSINESS_GOAL)
    payload.setdefault("goal_id", DEFAULT_GOAL_ID)
    payload["planning_horizon_days"] = _planning_horizon(payload.get("planning_horizon_days"))
    return payload


def _planning_horizon(value: Any) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = 90
    return max(30, min(days, 365))


def resolve_input_file(context: dict[str, Any], key: str, fallback_name: str) -> Path:
    inputs = normalized_inputs(context)
    value = str(inputs.get(key) or "").strip()
    root_value = str(inputs.get("input_folder") or "").strip()
    blueprint_dir = Path(context["blueprint_dir"])
    if value:
        return _resolve_path(blueprint_dir, value)
    root = _resolve_path(blueprint_dir, root_value) if root_value else blueprint_dir / "examples" / "sample_inputs"
    return (root / fallback_name).resolve()


def json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def source_descriptor(path: Path, *, synthetic: bool) -> dict[str, Any]:
    return {
        "source_ref": f"input:{path.name}",
        "timestamp": "not_reported",
        "coverage_period": "not_reported",
        "data_quality_note": (
            "Bundled synthetic demo; do not treat as measured business evidence."
            if synthetic
            else "User-supplied confidential input; authorization, provenance, and consent require operator review."
        ),
    }


def _resolve_path(blueprint_dir: Path, value: str) -> Path:
    if value.startswith("@/"):
        return (blueprint_dir / value[2:]).resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = blueprint_dir / candidate
    return candidate.resolve()
