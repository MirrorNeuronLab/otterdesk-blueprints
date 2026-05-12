from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import DEFAULT_RUNS_ROOT, LEGACY_RUNS_ROOT
from .utils import read_json_file


def list_runs(
    *,
    runs_root: str | Path | None = None,
    blueprint_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    roots = run_roots(runs_root)
    if not roots:
        return []
    rows = []
    for root in roots:
        for run_json in root.glob("*/run.json"):
            try:
                record = read_json_file(run_json)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if blueprint_id and record.get("blueprint_id") != blueprint_id:
                continue
            record.setdefault("run_id", run_json.parent.name)
            record.setdefault("run_dir", str(run_json.parent))
            web_ui_path = run_json.parent / "web_ui.json"
            if web_ui_path.exists():
                try:
                    record["web_ui"] = read_json_file(web_ui_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    record["web_ui"] = {}
            job_path = run_json.parent / "job.json"
            if job_path.exists():
                try:
                    record["job"] = read_json_file(job_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    record["job"] = {}
            rows.append(record)
    rows.sort(key=lambda item: item.get("ended_at") or item.get("started_at") or "", reverse=True)
    return rows[:limit] if limit is not None else rows


def read_run_events(run_id: str, *, runs_root: str | Path | None = None) -> list[dict[str, Any]]:
    events_path = run_dir(run_id, runs_root) / "events.jsonl"
    if not events_path.exists():
        return []
    events = []
    for line in events_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def load_run(run_id: str, *, runs_root: str | Path | None = None) -> dict[str, Any]:
    directory = run_dir(run_id, runs_root)
    if not directory.exists():
        searched = ", ".join(str(root) for root in run_roots(runs_root))
        raise FileNotFoundError(f"run {run_id!r} not found under {searched}")
    run = read_json_file(directory / "run.json") if (directory / "run.json").exists() else {}
    run.setdefault("run_id", run_id)
    run.setdefault("run_dir", str(directory))
    return {
        "run": run,
        "config": read_json_file(directory / "config.json") if (directory / "config.json").exists() else {},
        "inputs": read_json_file(directory / "inputs.json") if (directory / "inputs.json").exists() else {},
        "events": read_run_events(run_id, runs_root=runs_root),
        "result": read_json_file(directory / "result.json") if (directory / "result.json").exists() else {},
        "final_artifact": read_json_file(directory / "final_artifact.json") if (directory / "final_artifact.json").exists() else {},
        "web_ui": read_json_file(directory / "web_ui.json") if (directory / "web_ui.json").exists() else {},
        "job": read_json_file(directory / "job.json") if (directory / "job.json").exists() else {},
    }


def summarize_run(record: dict[str, Any]) -> dict[str, Any]:
    run = record.get("run") if "run" in record else record
    web_ui = run.get("web_ui") or record.get("web_ui") or {}
    return {
        "run_id": run.get("run_id"),
        "blueprint_id": run.get("blueprint_id"),
        "status": run.get("status"),
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "run_dir": run.get("run_dir"),
        "web_ui_url": web_ui.get("url"),
        "job_id": (record.get("job") or {}).get("job_id"),
    }


def run_dir(run_id: str, runs_root: str | Path | None = None) -> Path:
    preferred = Path(runs_root or DEFAULT_RUNS_ROOT).expanduser() / run_id
    if preferred.exists() or runs_root is not None:
        return preferred
    legacy = LEGACY_RUNS_ROOT.expanduser() / run_id
    return legacy if legacy.exists() else preferred


def run_roots(runs_root: str | Path | None = None) -> list[Path]:
    if runs_root is not None:
        root = Path(runs_root).expanduser()
        return [root] if root.exists() else []
    preferred = DEFAULT_RUNS_ROOT.expanduser()
    legacy = LEGACY_RUNS_ROOT.expanduser()
    roots = [preferred] if preferred.exists() else []
    if legacy.exists() and legacy != preferred:
        roots.append(legacy)
    return roots


_run_dir = run_dir
