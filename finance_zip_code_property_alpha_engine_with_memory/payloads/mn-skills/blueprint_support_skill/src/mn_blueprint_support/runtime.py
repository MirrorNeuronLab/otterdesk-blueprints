from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import CONFIG_SECTIONS, EXECUTION_MODEL, INPUT_ADAPTERS, OUTPUT_ADAPTERS, RUN_ARTIFACTS, WEB_UI_ADAPTERS
from .run_store import RunStore
from .utils import human_label


@dataclass
class BlueprintRuntimeContext:
    blueprint_id: str
    name: str
    run_id: str
    config: dict[str, Any]
    inputs: dict[str, Any]
    input_source: dict[str, Any]
    run_store: RunStore
    user_config: dict[str, Any] | None = None

    @property
    def run_dir(self) -> Path | None:
        return self.run_store.run_dir if self.run_store.enabled else None

    def start(self) -> None:
        self.run_store.start(config=self.config, inputs=self.inputs)

    def event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.run_store.event(event_type, payload)

    def finish(self, result: dict[str, Any]) -> None:
        self.run_store.finish(result)

    def fail(self, error: BaseException) -> None:
        self.run_store.fail(error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "name": self.name,
            "run_id": self.run_id,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "input_source": self.input_source,
        }


def resolve_output_adapter(blueprint_id: str, config: dict[str, Any]) -> RunStore:
    adapter = str((config.get("outputs") or {}).get("adapter") or "local_run_store")
    if adapter != "local_run_store":
        raise ValueError(f"unknown output adapter {adapter!r}")
    return RunStore.from_config(blueprint_id, config)


def create_runtime_context(
    blueprint_id: str,
    config: dict[str, Any],
    inputs: dict[str, Any],
    input_source: dict[str, Any],
    *,
    user_config: dict[str, Any] | None = None,
) -> BlueprintRuntimeContext:
    run_store = resolve_output_adapter(blueprint_id, config)
    identity = config.setdefault("identity", {})
    name = str(identity.get("name") or human_label(blueprint_id))
    return BlueprintRuntimeContext(
        blueprint_id=blueprint_id,
        name=name,
        run_id=run_store.run_id,
        config=config,
        inputs=inputs,
        input_source=input_source,
        run_store=run_store,
        user_config=user_config,
    )


def architecture_contract(config: dict[str, Any], input_source: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata": "manifest.json and product catalog",
        "config": {
            "standard_version": config.get("standard_version"),
            "mode": config.get("mode"),
            "identity": config.get("identity"),
        },
        "inputs": {
            "adapter": input_source.get("adapter"),
            "source": input_source,
        },
        "simulation_logic": config.get("simulation"),
        "optimization_model": config.get("optimization") or (config.get("simulation") or {}).get("optimization_model"),
        "llm_agents": config.get("llm"),
        "outputs": config.get("outputs"),
        "logging": config.get("logging"),
        "execution_model": list(EXECUTION_MODEL),
        "interfaces": {
            "identity_fields": ["blueprint_id", "name", "run_id"],
            "config_sections": list(CONFIG_SECTIONS),
            "input_adapters": list(INPUT_ADAPTERS),
            "output_adapters": list(OUTPUT_ADAPTERS),
            "web_ui_adapters": list(WEB_UI_ADAPTERS),
            "run_artifacts": list(RUN_ARTIFACTS),
        },
        "web_ui": config.get("web_ui"),
    }
