#!/usr/bin/env python3.11
from __future__ import annotations

import json
import os
from pathlib import Path

from continuous_service import deep_merge, main as service_main


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


if __name__ == "__main__":
    config_path = run_dir() / "resolved_service_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(load_config(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    service_main(["--config", str(config_path), "--run-dir", str(run_dir())])
