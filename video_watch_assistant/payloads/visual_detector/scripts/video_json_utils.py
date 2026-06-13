from __future__ import annotations

import json
import re
from typing import Any


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
