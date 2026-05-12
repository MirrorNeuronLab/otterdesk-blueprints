from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_config
from .runtime import BlueprintRuntimeContext, create_runtime_context
from .utils import human_label, utc_now_iso


@dataclass
class WorkerRunContract:
    blueprint_id: str
    name: str
    inputs: dict[str, Any]
    input_source: dict[str, Any]
    config: dict[str, Any] | None = None
    context: BlueprintRuntimeContext | None = None
    unavailable_reason: str | None = None
    started_at: str | None = None

    @property
    def available(self) -> bool:
        return self.context is not None

    @property
    def run_store_enabled(self) -> bool:
        return bool(self.context and self.context.run_store.enabled)

    @property
    def run_id(self) -> str | None:
        return self.context.run_id if self.context else None

    @property
    def run_dir(self) -> Path | None:
        return self.context.run_dir if self.context else None

    def start(self) -> None:
        self.started_at = utc_now_iso()
        if self.context:
            self.context.start()

    def event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.context:
            self.context.event(event_type, payload)

    def finish(self, result: dict[str, Any]) -> dict[str, Any]:
        self.enrich_result(result, status="completed")
        if self.context:
            self.context.finish(result)
        return result

    def fail(self, error: BaseException) -> None:
        if self.context:
            self.context.fail(error)

    def enrich_result(self, result: dict[str, Any], *, status: str) -> dict[str, Any]:
        identity = result.setdefault("identity", {})
        if isinstance(identity, dict):
            identity.setdefault("blueprint_id", self.blueprint_id)
            identity.setdefault("name", self.name)
            if self.run_id:
                identity.setdefault("run_id", self.run_id)

        result.setdefault("blueprint", self.blueprint_id)
        result.setdefault("name", self.name)
        result.setdefault("inputs", self.inputs)
        result.setdefault("input_source", self.input_source)

        run = result.setdefault("run", {})
        if isinstance(run, dict):
            if self.run_id:
                run.setdefault("run_id", self.run_id)
            run.setdefault("run_dir", str(self.run_dir) if self.run_dir else None)
            run.setdefault("started_at", self.started_at)
            run.setdefault("ended_at", utc_now_iso())
            run.setdefault("status", status)

        result["shared_run_contract"] = self.to_dict()
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "run_store_enabled": self.run_store_enabled,
            "blueprint_id": self.blueprint_id,
            "name": self.name,
            "run_id": self.run_id,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "input_source": self.input_source,
            "unavailable_reason": self.unavailable_reason,
        }


def create_worker_run_contract(
    blueprint_id: str,
    *,
    name: str | None = None,
    inputs: dict[str, Any] | None = None,
    input_source: dict[str, Any] | None = None,
    default_config_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    write_run_store: bool | None = None,
) -> WorkerRunContract:
    effective_inputs = dict(inputs or {})
    effective_source = dict(input_source or {"adapter": "custom_worker", "real_ready": True})
    effective_name = name or human_label(blueprint_id)
    resolved_config = load_config(
        blueprint_id,
        default_config_path=default_config_path,
        config=config,
        config_path=config_path,
        config_json=config_json,
        runs_root=runs_root,
        run_id=run_id,
        input_payload=effective_inputs,
        write_run_store=write_run_store,
    )
    resolved_config.setdefault("identity", {})["name"] = effective_name
    context = create_runtime_context(
        blueprint_id,
        resolved_config,
        effective_inputs,
        effective_source,
    )
    return WorkerRunContract(
        blueprint_id=blueprint_id,
        name=effective_name,
        inputs=effective_inputs,
        input_source=effective_source,
        config=resolved_config,
        context=context,
    )


def create_worker_run_contract_from_environment(
    blueprint_id: str,
    *,
    name: str | None = None,
    inputs: dict[str, Any] | None = None,
    input_source: dict[str, Any] | None = None,
    default_config_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    write_run_store: bool | None = None,
) -> WorkerRunContract:
    if run_id is None:
        run_id = os.environ.get("MN_RUN_ID")
    if runs_root is None:
        runs_root = os.environ.get("MN_RUNS_ROOT")
    if config_path is None:
        config_path = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if config_json is None:
        config_json = os.environ.get("MN_BLUEPRINT_CONFIG_JSON")
    if write_run_store is None and (
        _env_flag("MN_NO_RUN_STORE") or _env_flag("MN_DISABLE_RUN_STORE")
    ):
        write_run_store = False

    return create_worker_run_contract(
        blueprint_id,
        name=name,
        inputs=inputs,
        input_source=input_source,
        default_config_path=default_config_path,
        config=config,
        config_path=config_path,
        config_json=config_json,
        run_id=run_id,
        runs_root=runs_root,
        write_run_store=write_run_store,
    )


def disabled_worker_run_contract(
    blueprint_id: str,
    *,
    name: str | None = None,
    inputs: dict[str, Any] | None = None,
    input_source: dict[str, Any] | None = None,
    reason: str,
) -> WorkerRunContract:
    return WorkerRunContract(
        blueprint_id=blueprint_id,
        name=name or human_label(blueprint_id),
        inputs=dict(inputs or {}),
        input_source=dict(input_source or {"adapter": "custom_worker", "real_ready": True}),
        unavailable_reason=reason,
    )


def _env_flag(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
