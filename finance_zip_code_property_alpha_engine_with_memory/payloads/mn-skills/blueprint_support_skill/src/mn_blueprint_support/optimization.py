from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any


def build_optimization_plan(
    model_config: dict[str, Any] | None,
    state: dict[str, float],
    inputs: dict[str, Any],
    valid_actions: set[str],
) -> dict[str, Any] | None:
    if not model_config or not model_config.get("enabled", True):
        return None

    model_type = str(model_config.get("model_type") or "linear_program")
    if model_type != "linear_program":
        return _unsupported_model(model_config, model_type)

    context = _business_context(model_config, state, inputs)
    actions = _action_parameters(model_config, inputs, valid_actions)
    if not actions:
        return _unavailable_plan(model_config, context, "no valid optimization actions were configured")

    pyomo_available = _is_pyomo_available()
    pyomo_result = _solve_with_pyomo(model_config, context, actions)
    if pyomo_result is not None:
        return pyomo_result

    solution = _solve_fractional_lp(context, actions)
    note = (
        "Install a Pyomo-compatible solver such as HiGHS to solve the declared model directly."
        if pyomo_available
        else "Install Pyomo and a solver such as HiGHS to solve the declared model directly."
    )
    return _plan_from_solution(
        model_config,
        context,
        actions,
        solution,
        status="fallback_optimal",
        solver="deterministic_fractional_lp",
        pyomo_available=pyomo_available,
        solver_available=False,
        pyomo_version=_pyomo_version() if pyomo_available else None,
        note=note,
    )


def _business_context(model_config: dict[str, Any], state: dict[str, float], inputs: dict[str, Any]) -> dict[str, float]:
    daily_demand = _float_input(inputs, model_config, "daily_demand_units", 650.0)
    planning_horizon = _float_input(inputs, model_config, "planning_horizon_days", 14.0)
    target_inventory_days = _float_input(inputs, model_config, "target_inventory_days", 22.0)
    target_delay_days = _float_input(inputs, model_config, "target_supplier_delay_days", 3.0)
    budget = _float_input(inputs, model_config, "optimization_budget_usd", _float_input(inputs, model_config, "budget_usd", 65000.0))
    unmet_penalty = _float_input(inputs, model_config, "unmet_penalty_usd", 75.0)
    delay_weight = _float_input(inputs, model_config, "delay_buffer_weight", 0.55)

    inventory_days = float(state.get("inventory_days", target_inventory_days))
    demand_index = float(state.get("demand_index", 100.0))
    supplier_delay_days = float(state.get("supplier_delay_days", target_delay_days))
    service_level = float(state.get("service_level", 90.0))

    inventory_units = max(inventory_days, 0.0) * daily_demand
    target_inventory_units = max(target_inventory_days, 0.0) * daily_demand
    demand_pressure_units = max(0.0, demand_index - 100.0) / 100.0 * planning_horizon * daily_demand
    delay_buffer_units = max(0.0, supplier_delay_days - target_delay_days) * daily_demand * delay_weight
    resilience_gap = max(0.0, target_inventory_units - inventory_units + demand_pressure_units + delay_buffer_units)

    return {
        "daily_demand_units": round(daily_demand, 3),
        "planning_horizon_days": round(planning_horizon, 3),
        "target_inventory_days": round(target_inventory_days, 3),
        "target_supplier_delay_days": round(target_delay_days, 3),
        "budget_usd": round(max(budget, 0.0), 3),
        "unmet_penalty_usd": round(max(unmet_penalty, 0.0), 3),
        "inventory_days": round(inventory_days, 3),
        "inventory_units": round(inventory_units, 3),
        "target_inventory_units": round(target_inventory_units, 3),
        "demand_index": round(demand_index, 3),
        "demand_pressure_units": round(demand_pressure_units, 3),
        "supplier_delay_days": round(supplier_delay_days, 3),
        "delay_buffer_units": round(delay_buffer_units, 3),
        "service_level": round(service_level, 3),
        "resilience_gap_units": round(resilience_gap, 3),
    }


def _action_parameters(
    model_config: dict[str, Any],
    inputs: dict[str, Any],
    valid_actions: set[str],
) -> dict[str, dict[str, float]]:
    actions: dict[str, dict[str, float]] = {}
    raw_actions = model_config.get("actions") or {}
    if not isinstance(raw_actions, dict):
        return actions

    for name, raw in raw_actions.items():
        if name not in valid_actions or not isinstance(raw, dict):
            continue
        unit_cost = _float_input(inputs, raw, f"{name}_unit_cost_usd", float(raw.get("unit_cost_usd", 0.0)))
        max_units = _float_input(inputs, raw, f"{name}_max_units", float(raw.get("max_units", 0.0)))
        effectiveness = _float_input(inputs, raw, f"{name}_effectiveness", float(raw.get("effectiveness", 1.0)))
        if unit_cost < 0 or max_units <= 0 or effectiveness <= 0:
            continue
        actions[name] = {
            "unit_cost_usd": round(unit_cost, 6),
            "max_units": round(max_units, 6),
            "effectiveness": round(effectiveness, 6),
            "service_gain_per_1000_units": round(float(raw.get("service_gain_per_1000_units", 0.0)), 6),
            "delay_reduction_days_per_1000_units": round(float(raw.get("delay_reduction_days_per_1000_units", 0.0)), 6),
            "inventory_drawdown_days_per_1000_units": round(float(raw.get("inventory_drawdown_days_per_1000_units", 0.0)), 6),
        }
    return actions


def _solve_with_pyomo(
    model_config: dict[str, Any],
    context: dict[str, float],
    actions: dict[str, dict[str, float]],
) -> dict[str, Any] | None:
    try:
        import pyomo.environ as pyo
    except ModuleNotFoundError:
        return None

    model = pyo.ConcreteModel(name=str(model_config.get("name") or "supply_chain_resilience_lp"))
    action_names = list(actions)
    model.actions = pyo.Set(initialize=action_names)
    model.units = pyo.Var(model.actions, domain=pyo.NonNegativeReals)
    model.unmet_units = pyo.Var(domain=pyo.NonNegativeReals)

    gap_units = float(context["resilience_gap_units"])
    budget = float(context["budget_usd"])
    penalty = float(context["unmet_penalty_usd"])

    model.capacity = pyo.Constraint(model.actions, rule=lambda m, action: m.units[action] <= actions[action]["max_units"])
    model.budget = pyo.Constraint(
        expr=sum(actions[action]["unit_cost_usd"] * model.units[action] for action in model.actions) <= budget
    )
    model.resilience_gap = pyo.Constraint(
        expr=sum(actions[action]["effectiveness"] * model.units[action] for action in model.actions) + model.unmet_units >= gap_units
    )
    model.objective = pyo.Objective(
        expr=sum(actions[action]["unit_cost_usd"] * model.units[action] for action in model.actions) + penalty * model.unmet_units,
        sense=pyo.minimize,
    )

    for solver_name in _solver_candidates(model_config):
        try:
            solver = pyo.SolverFactory(solver_name)
            if not solver.available(False):
                continue
            raw_result = solver.solve(model, tee=False)
        except Exception:
            continue

        termination = str(getattr(raw_result.solver, "termination_condition", "")).lower()
        if "optimal" not in termination and "feasible" not in termination:
            continue

        values = {action: max(0.0, float(pyo.value(model.units[action]))) for action in action_names}
        solution = {
            "values": values,
            "unmet_units": max(0.0, float(pyo.value(model.unmet_units))),
        }
        return _plan_from_solution(
            model_config,
            context,
            actions,
            solution,
            status="optimal" if "optimal" in termination else "feasible",
            solver=solver_name,
            pyomo_available=True,
            solver_available=True,
            pyomo_version=_pyomo_version(),
        )

    return None


def _solve_fractional_lp(context: dict[str, float], actions: dict[str, dict[str, float]]) -> dict[str, Any]:
    remaining_gap = max(0.0, float(context["resilience_gap_units"]))
    remaining_budget = max(0.0, float(context["budget_usd"]))
    penalty = max(0.0, float(context["unmet_penalty_usd"]))
    values = {action: 0.0 for action in actions}

    ranked = sorted(
        actions.items(),
        key=lambda item: (
            (penalty * item[1]["effectiveness"] - item[1]["unit_cost_usd"]) / max(item[1]["unit_cost_usd"], 0.000001),
            item[1]["effectiveness"] / max(item[1]["unit_cost_usd"], 0.000001),
        ),
        reverse=True,
    )

    for action, params in ranked:
        unit_cost = params["unit_cost_usd"]
        effectiveness = params["effectiveness"]
        if remaining_gap <= 0:
            break
        if penalty * effectiveness <= unit_cost:
            continue
        affordable_units = remaining_budget / unit_cost if unit_cost else params["max_units"]
        units = min(params["max_units"], remaining_gap / effectiveness, affordable_units)
        if units <= 0:
            continue
        values[action] = units
        remaining_gap = max(0.0, remaining_gap - units * effectiveness)
        remaining_budget = max(0.0, remaining_budget - units * unit_cost)

    return {
        "values": values,
        "unmet_units": remaining_gap,
    }


def _plan_from_solution(
    model_config: dict[str, Any],
    context: dict[str, float],
    actions: dict[str, dict[str, float]],
    solution: dict[str, Any],
    *,
    status: str,
    solver: str,
    pyomo_available: bool,
    solver_available: bool,
    pyomo_version: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    values = {action: float(value) for action, value in (solution.get("values") or {}).items()}
    unmet_units = max(0.0, float(solution.get("unmet_units", 0.0)))
    variables = []
    total_cost = 0.0
    covered_units = 0.0
    service_gain = 0.0
    delay_reduction = 0.0
    inventory_drawdown = 0.0

    for action, params in actions.items():
        units = max(0.0, values.get(action, 0.0))
        effective_units = units * params["effectiveness"]
        cost = units * params["unit_cost_usd"]
        total_cost += cost
        covered_units += effective_units
        service_gain += units / 1000.0 * params.get("service_gain_per_1000_units", 0.0)
        delay_reduction += units / 1000.0 * params.get("delay_reduction_days_per_1000_units", 0.0)
        inventory_drawdown += units / 1000.0 * params.get("inventory_drawdown_days_per_1000_units", 0.0)
        variables.append(
            {
                "name": f"units[{action}]",
                "action": action,
                "value": round(units, 3),
                "effective_units": round(effective_units, 3),
                "unit_cost_usd": round(params["unit_cost_usd"], 3),
                "cost_usd": round(cost, 2),
                "capacity_units": round(params["max_units"], 3),
            }
        )

    variables.sort(key=lambda item: item["effective_units"], reverse=True)
    budget = float(context["budget_usd"])
    gap_units = float(context["resilience_gap_units"])
    current_service = float(context["service_level"])
    current_delay = float(context["supplier_delay_days"])
    current_inventory_days = float(context["inventory_days"])
    daily_demand = max(float(context["daily_demand_units"]), 0.000001)
    fill_rate = 1.0 if gap_units <= 0 else min(1.0, covered_units / gap_units)
    recommended = next((item["action"] for item in variables if item["value"] > 0.0001), None)

    constraints = [
        {
            "name": "resilience_gap",
            "required_units": round(gap_units, 3),
            "covered_units": round(covered_units, 3),
            "unmet_units": round(unmet_units, 3),
        },
        {
            "name": "budget",
            "limit_usd": round(budget, 2),
            "used_usd": round(total_cost, 2),
            "slack_usd": round(max(0.0, budget - total_cost), 2),
        },
    ]
    constraints.extend(
        {
            "name": f"capacity[{action}]",
            "limit_units": round(params["max_units"], 3),
            "used_units": round(values.get(action, 0.0), 3),
            "slack_units": round(max(0.0, params["max_units"] - values.get(action, 0.0)), 3),
        }
        for action, params in actions.items()
    )

    return {
        "language": str(model_config.get("language") or "Pyomo"),
        "model_type": str(model_config.get("model_type") or "linear_program"),
        "name": str(model_config.get("name") or "supply_chain_resilience_lp"),
        "status": status,
        "solver": solver,
        "pyomo_available": pyomo_available,
        "solver_available": solver_available,
        "pyomo_version": pyomo_version,
        "note": note,
        "business_context": context,
        "objective": {
            "sense": "minimize",
            "value_usd": round(total_cost + float(context["unmet_penalty_usd"]) * unmet_units, 2),
            "components": {
                "mitigation_cost_usd": round(total_cost, 2),
                "unmet_penalty_usd": round(float(context["unmet_penalty_usd"]) * unmet_units, 2),
            },
        },
        "decision_variables": variables,
        "constraints": constraints,
        "recommended_action": recommended,
        "recommended_actions": [item["action"] for item in variables if item["value"] > 0.0001],
        "expected_outcome": {
            "covered_resilience_gap_units": round(covered_units, 3),
            "unmet_resilience_gap_units": round(unmet_units, 3),
            "gap_fill_rate": round(fill_rate, 4),
            "projected_service_level": round(min(100.0, current_service + service_gain), 3),
            "projected_supplier_delay_days": round(max(0.0, current_delay - delay_reduction), 3),
            "projected_inventory_days": round(max(0.0, current_inventory_days + covered_units / daily_demand - inventory_drawdown), 3),
        },
        "model_summary": (
            "Minimize mitigation cost plus unmet resilience-gap penalty while respecting budget, "
            "lane capacity, and action effectiveness constraints."
        ),
    }


def _solver_candidates(model_config: dict[str, Any]) -> list[str]:
    configured = str(model_config.get("solver") or "auto").strip()
    candidates: list[str] = []
    if configured and configured != "auto":
        candidates.append(configured)
    candidates.extend(["appsi_highs", "highs", "glpk", "cbc"])
    unique: list[str] = []
    for item in candidates:
        if item not in unique:
            unique.append(item)
    return unique


def _pyomo_version() -> str | None:
    try:
        return version("pyomo")
    except PackageNotFoundError:
        return None


def _is_pyomo_available() -> bool:
    try:
        import pyomo.environ  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _float_input(inputs: dict[str, Any], config: dict[str, Any], key: str, default: float) -> float:
    value = inputs.get(key, config.get(key, default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _unsupported_model(model_config: dict[str, Any], model_type: str) -> dict[str, Any]:
    return {
        "language": str(model_config.get("language") or "Pyomo"),
        "model_type": model_type,
        "status": "unsupported",
        "solver": None,
        "pyomo_available": False,
        "solver_available": False,
        "business_context": {},
        "decision_variables": [],
        "constraints": [],
        "recommended_action": None,
        "recommended_actions": [],
        "expected_outcome": {},
        "note": f"Unsupported optimization model type: {model_type}.",
    }


def _unavailable_plan(model_config: dict[str, Any], context: dict[str, float], note: str) -> dict[str, Any]:
    return {
        "language": str(model_config.get("language") or "Pyomo"),
        "model_type": str(model_config.get("model_type") or "linear_program"),
        "name": str(model_config.get("name") or "supply_chain_resilience_lp"),
        "status": "unavailable",
        "solver": None,
        "pyomo_available": False,
        "solver_available": False,
        "business_context": context,
        "decision_variables": [],
        "constraints": [],
        "recommended_action": None,
        "recommended_actions": [],
        "expected_outcome": {},
        "note": note,
    }
