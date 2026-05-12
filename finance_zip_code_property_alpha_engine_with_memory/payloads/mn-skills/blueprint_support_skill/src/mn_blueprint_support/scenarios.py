from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog_loader import load_blueprint_json, load_blueprint_json_files
from .product_catalog import LEGACY_ALIASES


@dataclass(frozen=True)
class MetricSpec:
    name: str
    initial: float
    drift: float
    volatility: float
    minimum: float
    maximum: float
    label: str


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    effects: dict[str, float]
    cost: float = 0.0


@dataclass(frozen=True)
class ScenarioSpec:
    blueprint_id: str
    category: str
    name: str
    description: str
    llm_role: str
    agent_responsibilities: tuple[str, ...]
    features: tuple[str, ...]
    metrics: tuple[MetricSpec, ...]
    actions: tuple[ActionSpec, ...]
    primary_metric: str
    objective: str
    risk_metric: str
    artifact_type: str
    entity_label: str
    entity_names: tuple[str, ...]
    default_inputs: dict[str, Any]
    requires_human_approval: bool = False
    uses_tool: bool = False
    multi_agent: bool = False
    optimization_model: dict[str, Any] | None = None


def metric(name: str, initial: float, drift: float, volatility: float, minimum: float, maximum: float, label: str) -> MetricSpec:
    return MetricSpec(name, initial, drift, volatility, minimum, maximum, label)


def action(name: str, description: str, effects: dict[str, float], cost: float = 0.0) -> ActionSpec:
    return ActionSpec(name, description, effects, cost)


def scenario_from_dict(payload: dict[str, Any]) -> ScenarioSpec:
    metrics = tuple(_metric_from_dict(item) for item in payload.get("metrics", []))
    actions = tuple(_action_from_dict(item) for item in payload.get("actions", []))
    if not metrics:
        raise ValueError(f"scenario {payload.get('blueprint_id')!r} must declare metrics")
    if not actions:
        raise ValueError(f"scenario {payload.get('blueprint_id')!r} must declare actions")
    return ScenarioSpec(
        blueprint_id=str(payload["blueprint_id"]),
        category=str(payload["category"]),
        name=str(payload.get("name") or payload["blueprint_id"]),
        description=str(payload.get("description") or ""),
        llm_role=str(payload["llm_role"]),
        agent_responsibilities=tuple(str(item) for item in payload.get("agent_responsibilities", [])),
        features=tuple(str(item) for item in payload.get("features", [])),
        metrics=metrics,
        actions=actions,
        primary_metric=str(payload["primary_metric"]),
        objective=str(payload["objective"]),
        risk_metric=str(payload["risk_metric"]),
        artifact_type=str(payload["artifact_type"]),
        entity_label=str(payload["entity_label"]),
        entity_names=tuple(str(item) for item in payload.get("entity_names", [])),
        default_inputs=dict(payload.get("default_inputs") or {}),
        requires_human_approval=bool(payload.get("requires_human_approval", False)),
        uses_tool=bool(payload.get("uses_tool", False)),
        multi_agent=bool(payload.get("multi_agent", False)),
        optimization_model=dict(payload.get("optimization_model") or {}) or None,
    )


def load_scenarios() -> dict[str, ScenarioSpec]:
    scenarios: dict[str, ScenarioSpec] = {}
    for blueprint_id, payload in load_blueprint_json_files("scenario.json").items():
        scenarios[blueprint_id] = scenario_from_dict(payload)
    return scenarios


def get_scenario(blueprint_id: str) -> ScenarioSpec:
    blueprint_id = LEGACY_ALIASES.get(blueprint_id, blueprint_id)
    env_payload = load_blueprint_json(blueprint_id, "scenario.json")
    if env_payload is not None:
        return scenario_from_dict(env_payload)
    try:
        return SCENARIOS[blueprint_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown blueprint {blueprint_id!r}; provide {blueprint_id}/scenario.json "
            "or MN_BLUEPRINT_SCENARIO_JSON"
        ) from exc


def _metric_from_dict(payload: dict[str, Any]) -> MetricSpec:
    return MetricSpec(
        name=str(payload["name"]),
        initial=float(payload["initial"]),
        drift=float(payload["drift"]),
        volatility=float(payload["volatility"]),
        minimum=float(payload["minimum"]),
        maximum=float(payload["maximum"]),
        label=str(payload["label"]),
    )


def _action_from_dict(payload: dict[str, Any]) -> ActionSpec:
    return ActionSpec(
        name=str(payload["name"]),
        description=str(payload["description"]),
        effects={str(key): float(value) for key, value in dict(payload.get("effects") or {}).items()},
        cost=float(payload.get("cost", 0.0)),
    )


SCENARIOS = load_scenarios()
REQUIRED_BLUEPRINT_IDS = tuple(SCENARIOS)
