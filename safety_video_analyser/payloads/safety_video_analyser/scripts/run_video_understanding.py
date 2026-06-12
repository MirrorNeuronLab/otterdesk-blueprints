#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
from pathlib import Path


RESULT_START = "__MN_RESULT_START__"
RESULT_END = "__MN_RESULT_END__"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def load_config() -> dict:
    raw = os.getenv("MN_BLUEPRINT_CONFIG_JSON", "{}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def resolve_runtime_path(path_value: str | None) -> Path:
    workdir = Path(os.getenv("MN_WORKDIR", ".")).resolve()
    if not path_value:
        return workdir / "mn_local_inputs" / "videos"
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return workdir / path


def video_records(video_dir: Path) -> list[dict]:
    if not video_dir.is_dir():
        return []
    records = []
    for path in sorted(video_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        size = path.stat().st_size
        records.append(
            {
                "logical_name": path.name,
                "relative_path": path.relative_to(video_dir).as_posix(),
                "size_bytes": size,
                "media_type": media_type(path.suffix),
                "safety_focus": infer_safety_focus(path.name),
            }
        )
    return records


def media_type(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".webm":
        return "video/webm"
    if suffix == ".mov":
        return "video/quicktime"
    return "application/octet-stream"


def infer_safety_focus(name: str) -> str:
    lowered = name.lower()
    if "safety" in lowered:
        return "workplace safety review"
    if "work" in lowered:
        return "worksite activity review"
    return "general safety review"


def emit_result(payload: dict, exit_code: int = 0) -> None:
    envelope = {
        "exit_code": exit_code,
        "stdout": json.dumps(payload, sort_keys=True),
        "stderr": "",
    }
    print(f"{RESULT_START}{json.dumps(envelope, sort_keys=True)}{RESULT_END}")


def main() -> int:
    config = load_config()
    input_folder = (
        config.get("video_inputs", {}).get("folder_path")
        if isinstance(config.get("video_inputs"), dict)
        else None
    )
    video_dir = resolve_runtime_path(input_folder)
    records = video_records(video_dir)
    output = {
        "schema": "otterdesk.safety_video_analysis.v1",
        "agent": "video_understanding_agent",
        "model": os.getenv("MN_VLM_MODEL") or os.getenv("MN_LLM_MODEL") or "unknown",
        "provider": os.getenv("MN_VLM_PROVIDER") or os.getenv("MN_LLM_PROVIDER") or "unknown",
        "video_dir": str(video_dir),
        "video_count": len(records),
        "videos": records,
        "summary": (
            f"Prepared safety review metadata for {len(records)} video file(s)."
            if records
            else "No staged video files were found."
        ),
    }
    Path("video_analysis.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    emit_result(output, 0 if records else 2)
    return 0 if records else 2


if __name__ == "__main__":
    raise SystemExit(main())
