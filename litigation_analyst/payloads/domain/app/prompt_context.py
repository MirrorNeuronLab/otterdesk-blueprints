"""Bound the model's evidence view while retaining the complete audit on disk."""

import json


def _preview(value):
    if isinstance(value, str):
        return value if len(value) <= 600 else value[:600] + " [preview truncated]"
    if isinstance(value, list):
        return [_preview(item) for item in value[:5]]
    if isinstance(value, dict):
        return {key: _preview(item) for key, item in value.items()}
    return value


def investigation_history(records, *, max_bytes=12000):
    """Keep newest observations; never shorten the manual the agent just requested."""
    selected = []
    remaining = max_bytes
    for record in reversed(records[-8:]):
        manual = record.get("action", {}).get("name") == "read_skill"
        candidate = record if manual else _preview(record)
        if candidate != record:
            candidate = {**candidate, "context_preview": True,
                         "coverage_note": "Evidence preview is incomplete. Retrieve an exact passage before citing; full result remains in the audit."}
        size = len(json.dumps(candidate, ensure_ascii=False).encode())
        if size > remaining:
            break
        selected.append(candidate)
        remaining -= size
    return list(reversed(selected))
