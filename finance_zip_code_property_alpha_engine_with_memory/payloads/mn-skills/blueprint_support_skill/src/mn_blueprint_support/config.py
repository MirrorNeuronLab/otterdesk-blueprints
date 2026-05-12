from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .constants import (
    CONFIG_SECTIONS,
    DEFAULT_RUNS_ROOT,
    EXECUTION_MODEL,
    INPUT_ADAPTERS,
    OUTPUT_ADAPTERS,
    RUN_ARTIFACTS,
    STANDARD_VERSION,
    WEB_UI_ADAPTERS,
)
from .utils import deep_merge, human_label, read_json_file
from .web_ui import default_web_ui_config, validate_web_ui_config


def default_config(blueprint_id: str) -> dict[str, Any]:
    return {
        "standard_version": STANDARD_VERSION,
        "identity": {
            "blueprint_id": blueprint_id,
            "name": human_label(blueprint_id),
        },
        "mode": "mock",
        "inputs": {
            "adapter": "mock",
            "description": "Default synthetic inputs bundled with the blueprint.",
            "payload": {},
        },
        "simulation": {
            "enabled": True,
            "deterministic": True,
            "seed_field": "seed",
        },
        "llm": {
            "mode": "ollama",
            "mock_mode": "fake",
            "model": "ollama/nemotron3:33b",
            "api_base": "http://192.168.4.173:11434",
        },
        "outputs": {
            "adapter": "local_run_store",
            "run_root": str(DEFAULT_RUNS_ROOT),
            "write_run_store": True,
        },
        "logging": {
            "level": "INFO",
            "events_jsonl": True,
            "redact_env_secrets": True,
        },
        "real_adapters": {
            "input_file": {
                "adapter": "file",
                "description": "Load JSON overrides from a local file path.",
                "path": None,
            },
            "inline_json": {
                "adapter": "json",
                "description": "Load overrides from an inline JSON object.",
                "payload": {},
            },
        },
        "web_ui": default_web_ui_config(),
        "interfaces": {
            "identity_fields": ["blueprint_id", "name", "run_id"],
            "config_sections": list(CONFIG_SECTIONS),
            "input_adapters": list(INPUT_ADAPTERS),
            "output_adapters": list(OUTPUT_ADAPTERS),
            "web_ui_adapters": list(WEB_UI_ADAPTERS),
            "run_artifacts": list(RUN_ARTIFACTS),
        },
        "execution_model": list(EXECUTION_MODEL),
    }


def validate_config(config: dict[str, Any], *, blueprint_id: str | None = None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def issue(field: str, message: str, severity: str = "error") -> None:
        issues.append({"severity": severity, "field": field, "message": message})

    if config.get("standard_version") != STANDARD_VERSION:
        issue("standard_version", f"expected {STANDARD_VERSION!r}")
    identity = config.get("identity")
    if not isinstance(identity, dict):
        issue("identity", "identity section is required")
    else:
        actual_id = identity.get("blueprint_id")
        if not actual_id:
            issue("identity.blueprint_id", "blueprint_id is required")
        if blueprint_id and actual_id != blueprint_id:
            issue("identity.blueprint_id", f"expected {blueprint_id!r}, found {actual_id!r}")
        if not identity.get("name"):
            issue("identity.name", "human-readable name is required")

    inputs = config.get("inputs")
    if not isinstance(inputs, dict):
        issue("inputs", "inputs section is required")
    elif inputs.get("adapter", "mock") not in INPUT_ADAPTERS:
        issue("inputs.adapter", f"must be one of {', '.join(INPUT_ADAPTERS)}")

    outputs = config.get("outputs")
    if not isinstance(outputs, dict):
        issue("outputs", "outputs section is required")
    else:
        if outputs.get("adapter", "local_run_store") not in OUTPUT_ADAPTERS:
            issue("outputs.adapter", f"must be one of {', '.join(OUTPUT_ADAPTERS)}")
        if not outputs.get("run_root"):
            issue("outputs.run_root", "run_root is required for local run storage")

    for section in ("simulation", "llm", "logging", "real_adapters"):
        if not isinstance(config.get(section), dict):
            issue(section, f"{section} section is required")

    web_ui = config.get("web_ui")
    if web_ui is not None and not isinstance(web_ui, dict):
        issue("web_ui", "web_ui section must be an object")
    else:
        for web_issue in validate_web_ui_config(config):
            issue(web_issue["field"], web_issue["message"], web_issue.get("severity", "error"))

    interfaces = config.get("interfaces")
    if not isinstance(interfaces, dict):
        issue("interfaces", "interfaces section is required", "warning")
    else:
        if tuple(interfaces.get("input_adapters") or ()) != INPUT_ADAPTERS:
            issue("interfaces.input_adapters", "declared input adapters do not match the shared standard", "warning")
        if tuple(interfaces.get("output_adapters") or ()) != OUTPUT_ADAPTERS:
            issue("interfaces.output_adapters", "declared output adapters do not match the shared standard", "warning")
        if tuple(interfaces.get("run_artifacts") or ()) != RUN_ARTIFACTS:
            issue("interfaces.run_artifacts", "declared run artifacts do not match the shared standard", "warning")
        if tuple(interfaces.get("web_ui_adapters") or WEB_UI_ADAPTERS) != WEB_UI_ADAPTERS:
            issue("interfaces.web_ui_adapters", "declared web UI adapters do not match the shared standard", "warning")

    execution_model = config.get("execution_model")
    if not isinstance(execution_model, list) or not set(EXECUTION_MODEL).issubset(set(execution_model)):
        issue("execution_model", "execution model should include the shared lifecycle steps", "warning")

    return issues


def config_summary(config: dict[str, Any]) -> dict[str, Any]:
    identity = config.get("identity") or {}
    inputs = config.get("inputs") or {}
    outputs = config.get("outputs") or {}
    llm = config.get("llm") or {}
    web_ui = config.get("web_ui") or {}
    web_input = web_ui.get("input") or {}
    web_output = web_ui.get("output") or {}
    return {
        "blueprint_id": identity.get("blueprint_id"),
        "name": identity.get("name"),
        "mode": config.get("mode"),
        "input_adapter": inputs.get("adapter"),
        "output_adapter": outputs.get("adapter"),
        "run_root": outputs.get("run_root"),
        "llm_mode": llm.get("mode"),
        "llm_model": llm.get("model"),
        "web_ui_enabled": web_ui.get("enabled"),
        "web_ui_input_adapter": web_input.get("adapter"),
        "web_ui_output_adapter": web_output.get("adapter"),
    }


def load_config(
    blueprint_id: str,
    *,
    default_config_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    runs_root: str | Path | None = None,
    run_id: str | None = None,
    input_adapter: str | None = None,
    input_file: str | Path | None = None,
    input_payload: dict[str, Any] | None = None,
    write_run_store: bool | None = None,
) -> dict[str, Any]:
    resolved = default_config(blueprint_id)
    if config_path is None:
        config_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if config_json is None:
        config_json = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if run_id is None:
        run_id = os.environ.get("MN_RUN_ID")

    if default_config_path:
        resolved = deep_merge(resolved, read_json_file(Path(default_config_path)))
    if config_path:
        resolved = deep_merge(resolved, read_json_file(Path(config_path)))
    if config_json:
        decoded = json.loads(config_json)
        if not isinstance(decoded, dict):
            raise ValueError("config_json must decode to a JSON object")
        resolved = deep_merge(resolved, decoded)
    if config:
        resolved = deep_merge(resolved, config)

    resolved.setdefault("identity", {})
    resolved["identity"]["blueprint_id"] = blueprint_id
    if not resolved["identity"].get("name") or resolved["identity"]["name"] == blueprint_id:
        resolved["identity"]["name"] = human_label(blueprint_id)
    if run_id:
        resolved["identity"]["run_id"] = run_id

    if input_adapter:
        resolved.setdefault("inputs", {})["adapter"] = input_adapter
    if input_file:
        resolved.setdefault("inputs", {})["adapter"] = "file"
        resolved["inputs"]["path"] = str(input_file)
    if input_payload:
        resolved.setdefault("inputs", {})["payload"] = input_payload
    if runs_root:
        resolved.setdefault("outputs", {})["run_root"] = str(runs_root)
    elif os.environ.get("MN_RUNS_ROOT"):
        resolved.setdefault("outputs", {})["run_root"] = os.environ["MN_RUNS_ROOT"]
    if write_run_store is not None:
        resolved.setdefault("outputs", {})["write_run_store"] = write_run_store

    revision = os.environ.get("MN_BLUEPRINT_REVISION")
    if revision:
        resolved.setdefault("metadata", {})["blueprint_revision"] = revision

    return resolved
