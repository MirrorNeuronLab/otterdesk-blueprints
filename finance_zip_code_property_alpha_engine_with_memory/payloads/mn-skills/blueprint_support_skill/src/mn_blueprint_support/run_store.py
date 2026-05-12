from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import DEFAULT_RUNS_ROOT
from .utils import make_run_id, utc_now_iso


@dataclass
class RunStore:
    blueprint_id: str
    run_id: str
    run_dir: Path
    enabled: bool = True
    blueprint_revision: str | None = None

    @classmethod
    def from_config(cls, blueprint_id: str, config: dict[str, Any]) -> "RunStore":
        identity = config.setdefault("identity", {})
        run_id = identity.get("run_id") or make_run_id(blueprint_id)
        identity["run_id"] = run_id
        outputs = config.get("outputs") or {}
        metadata = config.get("metadata") or {}
        enabled = bool(outputs.get("write_run_store", True))
        run_root = Path(outputs.get("run_root") or DEFAULT_RUNS_ROOT).expanduser()
        return cls(
            blueprint_id=blueprint_id,
            run_id=run_id,
            run_dir=run_root / run_id,
            enabled=enabled,
            blueprint_revision=metadata.get("blueprint_revision"),
        )

    def start(self, *, config: dict[str, Any], inputs: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.write_json("config.json", config)
        self.write_json("inputs.json", inputs)
        self.write_json(
            "run.json",
            {
                "run_id": self.run_id,
                "blueprint_id": self.blueprint_id,
                "blueprint_revision": self.blueprint_revision or (config.get("metadata") or {}).get("blueprint_revision"),
                "status": "running",
                "started_at": utc_now_iso(),
                "run_dir": str(self.run_dir),
            },
        )
        self.event("run_started", {"blueprint_id": self.blueprint_id})
        self.event("inputs_loaded", {"input_keys": sorted(inputs)})

    def event(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": utc_now_iso(),
            "run_id": self.run_id,
            "blueprint_id": self.blueprint_id,
            "type": event_type,
            "payload": payload,
        }
        with (self.run_dir / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def finish(self, result: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.write_json("result.json", result)
        self.write_json("final_artifact.json", result.get("final_artifact") or {})
        summary = {
            "run_id": self.run_id,
            "blueprint_id": self.blueprint_id,
            "blueprint_revision": self.blueprint_revision
            or ((result.get("config") or {}).get("metadata") or {}).get("blueprint_revision")
            or ((result.get("architecture") or {}).get("config") or {}).get("blueprint_revision")
            or ((result.get("metadata") or {}).get("blueprint_revision")),
            "status": "completed",
            "started_at": result.get("run", {}).get("started_at"),
            "ended_at": result.get("run", {}).get("ended_at") or utc_now_iso(),
            "run_dir": str(self.run_dir),
            "result_path": str(self.run_dir / "result.json"),
            "final_artifact_path": str(self.run_dir / "final_artifact.json"),
        }
        self.write_json("run.json", summary)
        self.event("run_completed", {"result_path": summary["result_path"]})

    def write_web_ui(self, web_ui: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.write_json("web_ui.json", web_ui)
        self.event("web_ui_available", web_ui)

    def fail(self, error: BaseException) -> None:
        if not self.enabled:
            return
        summary = {
            "run_id": self.run_id,
            "blueprint_id": self.blueprint_id,
            "status": "failed",
            "ended_at": utc_now_iso(),
            "run_dir": str(self.run_dir),
            "error": {
                "type": error.__class__.__name__,
                "message": str(error),
            },
        }
        self.write_json("run.json", summary)
        self.event("run_failed", summary["error"])

    def write_json(self, name: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / name
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)
