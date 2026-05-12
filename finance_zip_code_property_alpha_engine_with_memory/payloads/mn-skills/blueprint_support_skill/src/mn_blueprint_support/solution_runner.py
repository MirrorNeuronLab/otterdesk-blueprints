from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

from .llm import LLMClient, get_llm_client
from .optimization import build_optimization_plan
from .scenarios import ActionSpec, ScenarioSpec, get_scenario
from .standard import architecture_contract, create_runtime_context, load_config, resolve_input_overrides, run_blueprint_cli, utc_now_iso
from .web_ui import maybe_write_static_output


def run_blueprint(
    blueprint_id: str,
    *,
    inputs: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    input_adapter: str | None = None,
    input_file: str | Path | None = None,
    write_run_store: bool | None = None,
) -> dict[str, Any]:
    spec = get_scenario(blueprint_id)
    started_at = utc_now_iso()
    default_config_path = _default_blueprint_config_path(spec.blueprint_id)
    resolved_config = load_config(
        spec.blueprint_id,
        default_config_path=default_config_path if default_config_path.exists() else None,
        config=config,
        config_path=config_path,
        config_json=config_json,
        runs_root=runs_root,
        run_id=run_id,
        input_adapter=input_adapter,
        input_file=input_file,
        write_run_store=write_run_store,
    )
    adapter_inputs, input_source = resolve_input_overrides(resolved_config)
    adapter_inputs.update(inputs or {})
    runtime_inputs = _merge_inputs(spec, adapter_inputs)
    steps = int(runtime_inputs.get("steps", 5))
    if steps <= 0:
        raise ValueError("steps must be greater than zero")

    rng = random.Random(int(runtime_inputs.get("seed", 42)))
    llm_mode = str((resolved_config.get("llm") or {}).get("mode") or "ollama")
    llm = llm_client or get_llm_client("fake" if llm_mode in {"fake", "mock"} else None)
    context = create_runtime_context(spec.blueprint_id, resolved_config, runtime_inputs, input_source)
    context.start()
    try:
        optimization_model = _resolve_optimization_model(spec, resolved_config)
        valid_actions = {item.name for item in spec.actions}
        state = _initial_state(spec, runtime_inputs)
        initial_state = copy.deepcopy(state)
        timeline: list[dict[str, Any]] = []

        for step in range(steps):
            context.event("simulation_step_started", {"step": step, "state_before": _rounded_metrics(state)})
            _advance_environment(spec, state, rng, step)
            optimization_plan = build_optimization_plan(optimization_model, state, runtime_inputs, valid_actions)
            if optimization_plan:
                context.event(
                    "optimization_model_solved",
                    {
                        "step": step,
                        "language": optimization_plan.get("language"),
                        "status": optimization_plan.get("status"),
                        "solver": optimization_plan.get("solver"),
                        "recommended_action": optimization_plan.get("recommended_action"),
                        "objective": optimization_plan.get("objective"),
                    },
                )
            observation = _build_observation(spec, state, step, runtime_inputs, optimization_plan=optimization_plan)
            heuristic = _heuristic_decision(spec, state, optimization_plan=optimization_plan)
            decision = _ask_agent(spec, observation, heuristic, llm)
            context.event("llm_decision", {"step": step, "decision": decision})
            human_gate = _apply_human_gate(spec, decision, runtime_inputs)
            applied_decision = human_gate["applied_decision"]
            _apply_action(spec, state, applied_decision["action"])
            entities = _rank_entities(spec, state, rng)
            state_after = _rounded_metrics(state)
            context.event(
                "simulation_state_updated",
                {"step": step, "applied_action": applied_decision["action"], "state_after": state_after},
            )
            timeline_entry = {
                "step": step,
                "observation": observation,
                "decision": applied_decision,
                "human_gate": human_gate if spec.requires_human_approval else None,
                "state_after": state_after,
                "ranked_entities": entities,
            }
            if optimization_plan:
                timeline_entry["optimization_plan"] = optimization_plan
            timeline.append(timeline_entry)

        state_changes = _state_changes(spec, initial_state, state)
        ended_at = utc_now_iso()
        result = {
            "identity": {
                "blueprint_id": context.blueprint_id,
                "name": context.name,
                "run_id": context.run_id,
            },
            "blueprint": spec.blueprint_id,
            "name": context.name,
            "category": spec.category,
            "description": spec.description,
            "run": {
                "run_id": context.run_id,
                "run_dir": str(context.run_dir) if context.run_dir else None,
                "started_at": started_at,
                "ended_at": ended_at,
                "status": "completed",
            },
            "architecture": architecture_contract(resolved_config, input_source),
            "config": resolved_config,
            "inputs": runtime_inputs,
            "input_source": input_source,
            "agent_roles": _agent_roles(spec),
            "runtime_features": list(spec.features),
            "uses_simulation": True,
            "uses_llm": True,
            "uses_optimization": bool(optimization_model),
            "timeline": timeline,
            "state_changes": state_changes,
            "final_artifact": _final_artifact(spec, initial_state, state, timeline, state_changes),
            "llm": {
                "provider": llm.provider,
                "model": llm.model,
                "calls": llm.calls,
                "fallback_calls": getattr(llm, "fallback_calls", 0),
            },
        }
        web_ui = maybe_write_static_output(context.run_store, result, resolved_config)
        if web_ui:
            result["web_ui"] = web_ui.to_dict()
        context.finish(result)
        return result
    except Exception as error:
        context.fail(error)
        raise


def main(argv: list[str] | None = None) -> None:
    run_blueprint_cli(
        run_blueprint,
        argv,
        description="Run a MirrorNeuron LLM simulation blueprint.",
    )


def _merge_inputs(spec: ScenarioSpec, overrides: dict[str, Any]) -> dict[str, Any]:
    inputs = dict(spec.default_inputs)
    inputs.update(overrides)
    for metric in spec.metrics:
        key = f"initial_{metric.name}"
        if key in inputs:
            inputs[key] = float(inputs[key])
    return inputs


def _resolve_optimization_model(spec: ScenarioSpec, config: dict[str, Any]) -> dict[str, Any] | None:
    model = dict(spec.optimization_model or {})
    config_model = config.get("optimization")
    if not isinstance(config_model, dict):
        config_model = (config.get("simulation") or {}).get("optimization_model")
    if isinstance(config_model, dict):
        model.update(config_model)
    return model or None


def _default_blueprint_config_path(blueprint_id: str) -> Path:
    relative = Path(blueprint_id) / "config" / "default.json"
    search_roots = [Path.cwd().resolve(), *Path(__file__).resolve().parents]
    for root in search_roots:
        for candidate in (
            root / relative,
            root / "mn-blueprints" / relative,
        ):
            if candidate.exists():
                return candidate
    return Path.cwd() / relative


def _initial_state(spec: ScenarioSpec, inputs: dict[str, Any]) -> dict[str, float]:
    state = {}
    for metric in spec.metrics:
        state[metric.name] = _clamp(float(inputs.get(f"initial_{metric.name}", metric.initial)), metric.minimum, metric.maximum)
    return state


def _advance_environment(spec: ScenarioSpec, state: dict[str, float], rng: random.Random, step: int) -> None:
    for index, metric in enumerate(spec.metrics):
        seasonal = ((step + index) % 3 - 1) * metric.volatility * 0.35
        noise = rng.uniform(-metric.volatility, metric.volatility)
        state[metric.name] = _clamp(
            state[metric.name] + metric.drift + seasonal + noise,
            metric.minimum,
            metric.maximum,
        )


def _build_observation(
    spec: ScenarioSpec,
    state: dict[str, float],
    step: int,
    inputs: dict[str, Any],
    *,
    optimization_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = _rounded_metrics(state)
    observation: dict[str, Any] = {
        "step": step,
        "metrics": metrics,
        "primary_metric": spec.primary_metric,
        "objective": spec.objective,
        "risk_metric": spec.risk_metric,
        "notable_events": _notable_events(spec, state),
    }
    if spec.uses_tool:
        observation["tool_result"] = _forecast_tool(spec, state, step)
    if optimization_plan:
        observation["optimization_plan"] = optimization_plan
    if spec.multi_agent:
        observation["agent_messages"] = [
            {"agent": "buyer", "message": f"Demand pressure is {metrics.get('demand_index', 0)} and budget discipline matters."},
            {"agent": "supplier", "message": f"Capacity is {metrics.get('supplier_capacity', 0)} and price must cover disruption risk."},
        ]
    if spec.requires_human_approval:
        observation["approval_policy"] = inputs.get("human_approval", "approve_high_confidence")
    return observation


def _heuristic_decision(
    spec: ScenarioSpec,
    state: dict[str, float],
    *,
    optimization_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    optimized_action = str((optimization_plan or {}).get("recommended_action") or "")
    if optimized_action and any(item.name == optimized_action for item in spec.actions):
        selected = next(item for item in spec.actions if item.name == optimized_action)
        expected = (optimization_plan or {}).get("expected_outcome") or {}
        objective = (optimization_plan or {}).get("objective") or {}
        return {
            "action": selected.name,
            "confidence": 0.82,
            "rationale": (
                f"The declared Pyomo optimization model selected {selected.name} after "
                f"balancing resilience gap coverage, budget, and lane capacity."
            ),
            "parameters": {
                "primary_metric": round(state[spec.primary_metric], 3),
                "risk_metric": round(state[spec.risk_metric], 3),
                "expected_effects": selected.effects,
                "optimization_status": optimization_plan.get("status"),
                "optimization_objective": objective,
                "expected_outcome": expected,
            },
        }
    best_action = max(spec.actions, key=lambda item: _score_action(spec, state, item))
    primary_value = state[spec.primary_metric]
    risk_value = state[spec.risk_metric]
    return {
        "action": best_action.name,
        "confidence": 0.74,
        "rationale": (
            f"{best_action.name} has the best simulated impact on {spec.primary_metric} "
            f"while watching {spec.risk_metric}."
        ),
        "parameters": {
            "primary_metric": round(primary_value, 3),
            "risk_metric": round(risk_value, 3),
            "expected_effects": best_action.effects,
        },
    }


def _score_action(spec: ScenarioSpec, state: dict[str, float], candidate: ActionSpec) -> float:
    primary_after = state[spec.primary_metric] + candidate.effects.get(spec.primary_metric, 0.0)
    risk_after = state[spec.risk_metric] + candidate.effects.get(spec.risk_metric, 0.0)
    primary_score = primary_after if spec.objective == "maximize" else -primary_after

    risk_metric = next(metric for metric in spec.metrics if metric.name == spec.risk_metric)
    risk_is_good_when_high = risk_metric.label.lower().endswith("percent") and "capacity" in risk_metric.name
    if spec.risk_metric in {"quality_score", "service_level", "retention_budget_pct", "approval_rate_pct", "liquidity_pct", "pump_capacity_pct", "measurement_confidence"}:
        risk_score = risk_after * 0.25
    elif risk_is_good_when_high:
        risk_score = risk_after * 0.15
    else:
        risk_score = -risk_after * 0.15
    return primary_score + risk_score - candidate.cost


def _ask_agent(spec: ScenarioSpec, observation: dict[str, Any], fallback: dict[str, Any], llm: LLMClient) -> dict[str, Any]:
    action_descriptions = {
        item.name: {"description": item.description, "effects": item.effects}
        for item in spec.actions
    }
    system_prompt = (
        f"You are the {spec.llm_role}. You control one step of a dynamic simulation. "
        "Return JSON with action, confidence, rationale, and parameters."
    )
    user_prompt = json.dumps(
        {
            "blueprint": spec.blueprint_id,
            "description": spec.description,
            "responsibilities": list(spec.agent_responsibilities),
            "observation": observation,
            "available_actions": action_descriptions,
            "fallback_policy": fallback,
        },
        indent=2,
        sort_keys=True,
    )
    response = llm.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)
    valid_actions = {item.name for item in spec.actions}
    action_name = str(response.get("action") or fallback["action"])
    if action_name not in valid_actions:
        action_name = fallback["action"]
    try:
        confidence = float(response.get("confidence", fallback.get("confidence", 0.7)))
    except (TypeError, ValueError):
        confidence = float(fallback.get("confidence", 0.7))
    return {
        "action": action_name,
        "confidence": round(_clamp(confidence, 0.0, 1.0), 3),
        "rationale": str(response.get("rationale") or fallback["rationale"]),
        "parameters": response.get("parameters") if isinstance(response.get("parameters"), dict) else fallback["parameters"],
        "provider": response.get("provider", llm.provider),
    }


def _apply_human_gate(spec: ScenarioSpec, decision: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    if not spec.requires_human_approval:
        return {"required": False, "approved": True, "applied_decision": decision}
    policy = str(inputs.get("human_approval", "approve_high_confidence"))
    approved = policy == "approve_all" or (policy == "approve_high_confidence" and decision["confidence"] >= 0.7)
    applied = dict(decision)
    if not approved:
        applied["action"] = "hold_policy" if any(item.name == "hold_policy" for item in spec.actions) else spec.actions[-1].name
        applied["rationale"] = f"Human approval gate blocked {decision['action']}; applied {applied['action']}."
    return {"required": True, "policy": policy, "approved": approved, "recommended_action": decision["action"], "applied_decision": applied}


def _apply_action(spec: ScenarioSpec, state: dict[str, float], action_name: str) -> None:
    selected = next((item for item in spec.actions if item.name == action_name), spec.actions[-1])
    metric_by_name = {metric.name: metric for metric in spec.metrics}
    for metric_name, effect in selected.effects.items():
        if metric_name not in state:
            continue
        metric = metric_by_name[metric_name]
        state[metric_name] = _clamp(state[metric_name] + effect, metric.minimum, metric.maximum)


def _rank_entities(spec: ScenarioSpec, state: dict[str, float], rng: random.Random) -> list[dict[str, Any]]:
    primary = state[spec.primary_metric]
    risk = state[spec.risk_metric]
    ranked = []
    for index, name in enumerate(spec.entity_names):
        base = primary if spec.objective == "maximize" else (100.0 - primary)
        risk_adjustment = -risk * 0.2 + rng.uniform(-3.0, 3.0)
        score = round(_clamp(base + risk_adjustment + index * 1.7, 0, 100), 2)
        ranked.append({"rank": index + 1, "name": name, "entity_type": spec.entity_label, "score": score})
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def _final_artifact(
    spec: ScenarioSpec,
    initial_state: dict[str, float],
    state: dict[str, float],
    timeline: list[dict[str, Any]],
    state_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    last = timeline[-1]
    best_entities = last["ranked_entities"][:3]
    actions = [item["decision"]["action"] for item in timeline]
    primary_delta = state[spec.primary_metric] - initial_state[spec.primary_metric]
    direction = "improved" if (primary_delta > 0 and spec.objective == "maximize") or (primary_delta < 0 and spec.objective == "minimize") else "worsened"
    next_steps = [
        f"Continue monitoring {spec.primary_metric} and {spec.risk_metric}.",
        f"Review top {spec.entity_label} option: {best_entities[0]['name']}.",
        "Run a longer simulation with live Ollama before production use.",
    ]
    optimization_plan = last.get("optimization_plan")
    if optimization_plan:
        next_steps.insert(1, "Review optimized quantities, budget slack, and unmet resilience gap before execution.")
    artifact = {
        "type": spec.artifact_type,
        "executive_summary": (
            f"{spec.name} ran {len(timeline)} simulated decision steps. "
            f"The primary metric {spec.primary_metric} {direction} from "
            f"{round(initial_state[spec.primary_metric], 3)} to {round(state[spec.primary_metric], 3)}."
        ),
        "recommended_action": actions[-1],
        "action_history": actions,
        "key_metrics": _rounded_metrics(state),
        "ranked_options": best_entities,
        "state_changes": state_changes,
        "next_steps": next_steps,
    }
    if optimization_plan:
        artifact["optimization_plan"] = _optimization_artifact_summary(optimization_plan)
    return artifact


def _optimization_artifact_summary(optimization_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "language": optimization_plan.get("language"),
        "model_type": optimization_plan.get("model_type"),
        "status": optimization_plan.get("status"),
        "solver": optimization_plan.get("solver"),
        "recommended_action": optimization_plan.get("recommended_action"),
        "recommended_actions": optimization_plan.get("recommended_actions") or [],
        "objective": optimization_plan.get("objective") or {},
        "business_context": optimization_plan.get("business_context") or {},
        "decision_variables": optimization_plan.get("decision_variables") or [],
        "expected_outcome": optimization_plan.get("expected_outcome") or {},
        "note": optimization_plan.get("note"),
    }


def _state_changes(spec: ScenarioSpec, initial_state: dict[str, float], state: dict[str, float]) -> list[dict[str, Any]]:
    changes = []
    for metric in spec.metrics:
        start = initial_state[metric.name]
        end = state[metric.name]
        changes.append(
            {
                "metric": metric.name,
                "label": metric.label,
                "start": round(start, 3),
                "end": round(end, 3),
                "delta": round(end - start, 3),
            }
        )
    return changes


def _agent_roles(spec: ScenarioSpec) -> list[dict[str, Any]]:
    roles = [
        {
            "role": spec.llm_role,
            "responsibilities": list(spec.agent_responsibilities),
            "llm_backing": "Ollama nemotron3:33b by default; fake adapter in tests",
        }
    ]
    if spec.multi_agent:
        roles.extend(
            [
                {"role": "Buyer constraint agent", "responsibilities": ["tracks budget", "states demand pressure"]},
                {"role": "Supplier constraint agent", "responsibilities": ["tracks capacity", "states price pressure"]},
            ]
        )
    return roles


def _notable_events(spec: ScenarioSpec, state: dict[str, float]) -> list[str]:
    events = []
    for metric in spec.metrics:
        value = state[metric.name]
        span = metric.maximum - metric.minimum
        if value >= metric.maximum - span * 0.15:
            events.append(f"{metric.label} is near the high bound")
        if value <= metric.minimum + span * 0.15:
            events.append(f"{metric.label} is near the low bound")
    return events or ["No hard threshold breached; continue observing trend."]


def _forecast_tool(spec: ScenarioSpec, state: dict[str, float], step: int) -> dict[str, Any]:
    return {
        "tool_name": "moving_window_forecast",
        "step": step,
        "forecast": {
            metric.name: round(
                _clamp(state[metric.name] + metric.drift * 2, metric.minimum, metric.maximum),
                3,
            )
            for metric in spec.metrics
        },
    }


def _rounded_metrics(state: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 3) for key, value in state.items()}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
