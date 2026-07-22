#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from continuous_service import deep_merge, main as service_main

_BEACON_LOCK = threading.Lock()
_BEACON_SEQUENCE = 0


def start_agent_beacon_thread(message: str | None = None) -> threading.Thread | None:
    """Keep the runtime liveness contract alive for the long-running service."""
    prefix = os.environ.get("MN_AGENT_BEACON_STDOUT_PREFIX")
    if not prefix:
        return None

    def emit(status: str) -> None:
        global _BEACON_SEQUENCE
        with _BEACON_LOCK:
            sequence = _BEACON_SEQUENCE
            _BEACON_SEQUENCE += 1
        payload = {
            "schema": "mn.agent.beacon.v1",
            "source": "agent",
            "status": status,
            "sequence": sequence,
            "pid": os.getpid(),
            "python": sys.executable,
            "message": message or "Continuous drug discovery service is running",
        }
        for env_name, field in (
            ("MN_AGENT_BEACON_JOB_ID", "job_id"),
            ("MN_AGENT_BEACON_AGENT_ID", "agent_id"),
            ("MN_AGENT_BEACON_STEP", "step"),
            ("MN_AGENT_BEACON_ATTEMPT", "attempt"),
        ):
            value = os.environ.get(env_name)
            if value:
                payload[field] = int(value) if field == "attempt" and value.isdigit() else value
        print(f"{prefix}{json.dumps(payload, separators=(',', ':'), sort_keys=True)}", flush=True)

    try:
        interval_milliseconds = int(os.environ.get("MN_AGENT_BEACON_INTERVAL_MS", "15000"))
    except (TypeError, ValueError):
        interval_milliseconds = 15000
    interval_seconds = max(interval_milliseconds / 1000.0, 0.1)

    def loop() -> None:
        while True:
            time.sleep(interval_seconds)
            emit("working")

    thread = threading.Thread(target=loop, name="mn-agent-beacon", daemon=True)
    thread.start()
    emit("started")
    return thread


def blueprint_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "config" / "default.json").exists():
            return parent
    return Path.cwd()


def resolved_config_path() -> Path:
    configured = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if configured and Path(configured).expanduser().exists():
        return Path(configured).expanduser()
    return blueprint_root() / "config" / "default.json"


def load_config() -> dict:
    config_path = resolved_config_path()
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        embedded = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
        if not embedded:
            raise FileNotFoundError(f"Blueprint config is unavailable at {config_path} and MN_BLUEPRINT_CONFIG_JSON is not set")
        config = json.loads(embedded)
    overwrite = blueprint_root() / "config" / "overwrite.json"
    if overwrite.exists() and config_path.exists():
        config = deep_merge(config, json.loads(overwrite.read_text(encoding="utf-8")))
    embedded = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if embedded:
        config = deep_merge(config, json.loads(embedded))
    return config


def run_dir() -> Path:
    configured = os.environ.get("MN_RUN_DIR")
    if configured:
        return Path(configured).expanduser()
    context_path = os.environ.get("MN_CONTEXT_FILE")
    if context_path:
        return Path(context_path).resolve().parent
    return Path.cwd() / "runs" / "continuous_drug_discovery_service"


def main() -> None:
    start_agent_beacon_thread("Continuous drug discovery service is running")
    config_path = run_dir() / "resolved_service_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(load_config(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    service_main(["--config", str(config_path), "--run-dir", str(run_dir())])


if __name__ == "__main__":
    main()
