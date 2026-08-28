"""Candidate research, cost modeling, risk review, and recommendation audit."""

from __future__ import annotations

import json
import re
from typing import Any

from mn_blueprint_support import resolve_actor_specs

from .llm_analysis import (
    analysis_settings,
    analysis_validation_context,
    candidate_analysis_packet,
    generate_structured_analysis,
    known_source_refs,
    validate_decision_analysis,
    validate_risk_analysis,
    validate_tco_analysis,
)
from .research import deterministic_evidence, deterministic_recommendation, research_public_sources
from .state import _inputs, _save, _state

def research_market(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = state.get("inputs") or _inputs(ctx)
    llm_config = ctx["config"].get("llm") if isinstance(ctx["config"].get("llm"), dict) else {}
    quick = str(llm_config.get("mode") or "live").lower() in {"fake", "mock"} or bool((ctx["config"].get("execution") or {}).get("quick_test"))
    sources, web_warnings = research_public_sources(
        state.get("research_queries") or [],
        ctx["config"],
        seed_urls=state.get("research_links") or [],
        quick_test=quick,
    )
    documents = state.get("documents") or []
    evidence = deterministic_evidence(inputs, documents, sources)
    state.update({"inputs": inputs, "sources": sources, "web_warnings": web_warnings, "evidence": evidence})
    _save(ctx, state)
    return {"source_count": len(sources), "query_count": len(state.get("research_queries") or [])}


def _candidate_records(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for document in documents:
        if str(document.get("suffix") or "").lower() != ".json":
            continue
        try:
            parsed = json.loads(str(document.get("text") or "{}"))
        except (TypeError, ValueError):
            continue
        values = parsed.get("candidates") if isinstance(parsed, dict) else None
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                candidate = dict(value)
                candidate.setdefault("source_ref", document.get("source_ref"))
                candidates.append(candidate)
    return candidates


def _money(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        matched = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
        if not matched:
            return None
        try:
            return round(float(matched.group(0).replace(",", "")), 2)
        except ValueError:
            return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        matched = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(matched.group(0)) if matched else None


def _rate(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if isinstance(value, str) and "%" in value:
        number /= 100
    return number


def _candidate_value(candidate: dict[str, Any], key: str) -> Any:
    if key in candidate:
        return candidate[key]
    aliases = {
        "min_warranty_years": "warranty_years",
        "local_delivery_required": "local_delivery_available",
        "local_setup_required": "local_setup_available",
        "local_pickup_required": "local_pickup_available",
        "shipping_required": "shipping_available",
        "available_for_purchase_required": "available_for_purchase",
        "max_lead_time_business_days": "lead_time_business_days",
    }
    if key in aliases and aliases[key] in candidate:
        return candidate[aliases[key]]
    specifications = candidate.get("specifications")
    if not isinstance(specifications, dict):
        return None
    return specifications.get(key, specifications.get(aliases.get(key, "")))


def _commercial_constraint_checks(
    inputs: dict[str, Any], candidate: dict[str, Any], quote_total: float | None
) -> dict[str, bool]:
    budget = _money(inputs.get("budget"))
    checks: dict[str, bool] = {
        "budget": budget is None or (quote_total is not None and quote_total <= budget),
    }
    for key, required in (inputs.get("constraints") or {}).items():
        if required in (None, ""):
            continue
        observed = _candidate_value(candidate, key)
        if key.startswith("min_"):
            observed_number = _number(observed)
            required_number = _number(required)
            checks[key] = bool(
                observed_number is not None
                and required_number is not None
                and observed_number >= required_number
            )
        elif key.startswith("max_"):
            observed_number = _number(observed)
            required_number = _number(required)
            checks[key] = bool(
                observed_number is not None
                and required_number is not None
                and observed_number <= required_number
            )
        elif key.endswith("_required"):
            checks[key] = bool(observed) is bool(required)
        else:
            checks[key] = str(observed or "").strip().lower() == str(required).strip().lower()
    return checks


def _analysis_parameters(inputs: dict[str, Any]) -> dict[str, Any]:
    raw = inputs.get("analysis") if isinstance(inputs.get("analysis"), dict) else {}
    parameters = {
        "horizon_years": max(1, int(_number(raw.get("horizon_years")) or 3)),
        "discount_rate": _rate(raw.get("discount_rate")) or 0.0,
        "tax_rate": _rate(raw.get("tax_rate")),
        "electricity_rate_per_kwh": _number(raw.get("electricity_rate_per_kwh")),
        "active_hours_per_year": _number(raw.get("active_hours_per_year")) or 0.0,
        "idle_hours_per_year": _number(raw.get("idle_hours_per_year")) or 0.0,
        "loaded_labor_cost_per_hour": _money(raw.get("loaded_labor_cost_per_hour")) or 0.0,
        "downtime_cost_per_hour": _money(raw.get("downtime_cost_per_hour")) or 0.0,
        "expected_downtime_hours_per_year": _number(raw.get("expected_downtime_hours_per_year")) or 0.0,
        "annual_maintenance_reserve": _money(raw.get("annual_maintenance_reserve")) or 0.0,
        "residual_value_percent": _rate(raw.get("residual_value_percent")) or 0.0,
        "scenarios": list(raw.get("scenarios") or []),
        "source_refs": list(raw.get("source_refs") or []),
    }
    for key in (
        "discount_rate",
        "tax_rate",
        "electricity_rate_per_kwh",
        "active_hours_per_year",
        "idle_hours_per_year",
        "loaded_labor_cost_per_hour",
        "downtime_cost_per_hour",
        "expected_downtime_hours_per_year",
        "annual_maintenance_reserve",
        "residual_value_percent",
    ):
        value = parameters.get(key)
        if value is not None and value < 0:
            raise ValueError(f"analysis.{key} must be non-negative")
    if parameters["residual_value_percent"] > 1:
        raise ValueError("analysis.residual_value_percent must be between 0 and 1")
    return parameters


def _present_value_annuity_factor(rate: float, years: int) -> float:
    if rate == 0:
        return float(years)
    return (1 - (1 + rate) ** -years) / rate


def _capital_recovery_factor(rate: float, years: int) -> float:
    if rate == 0:
        return 1 / years
    growth = (1 + rate) ** years
    return rate * growth / (growth - 1)


def _mandatory_option_cost(candidate: dict[str, Any]) -> float:
    return round(
        sum(
            _money(item.get("cost")) or 0.0
            for item in candidate.get("mandatory_options") or []
            if isinstance(item, dict)
        ),
        2,
    )


def _cost_metrics(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> dict[str, Any]:
    horizon = parameters["horizon_years"]
    discount_rate = parameters["discount_rate"]
    observed_base_price = _money(
        candidate.get("quote_subtotal", candidate.get("asking_price"))
    )
    base_price = observed_base_price or 0.0
    mandatory_options = _mandatory_option_cost(candidate)
    shipping = _money(candidate.get("shipping_cost")) or 0.0
    supplier_setup = _money(candidate.get("setup_cost")) or 0.0
    other_acquisition = _money(candidate.get("other_acquisition_cost")) or 0.0
    taxable_vendor_cost = round(
        base_price + mandatory_options + shipping + supplier_setup + other_acquisition,
        2,
    )
    explicit_tax = _money(candidate.get("sales_tax_estimate"))
    tax_rate = _rate(candidate.get("tax_rate"))
    if tax_rate is None:
        tax_rate = parameters.get("tax_rate")
    landed_cost_input_complete = observed_base_price is not None and (
        explicit_tax is not None or tax_rate is not None
    )
    sales_tax = explicit_tax
    if sales_tax is None and tax_rate is not None:
        sales_tax = round(taxable_vendor_cost * tax_rate, 2)
    sales_tax = sales_tax or 0.0
    vendor_cash_cost = round(taxable_vendor_cost + sales_tax, 2)

    labor_hours = candidate.get("internal_labor_hours") or {}
    if not isinstance(labor_hours, dict):
        labor_hours = {}
    total_internal_hours = sum(
        _number(value) or 0.0 for value in labor_hours.values()
    )
    internal_implementation = round(
        total_internal_hours * parameters["loaded_labor_cost_per_hour"], 2
    )
    landed_acquisition = round(vendor_cash_cost + internal_implementation, 2)

    power = candidate.get("power_model") or {}
    if not isinstance(power, dict):
        power = {}
    active_power_watts = sum(
        _number(power.get(key)) or 0.0
        for key in (
            "gpu_tgp_watts",
            "cpu_tdp_watts",
            "system_overhead_planning_watts",
        )
    )
    idle_power_watts = _number(power.get("idle_system_planning_watts")) or 0.0
    annual_kwh = round(
        (
            active_power_watts * parameters["active_hours_per_year"]
            + idle_power_watts * parameters["idle_hours_per_year"]
        )
        / 1000,
        2,
    )
    electricity_rate = parameters.get("electricity_rate_per_kwh")
    annual_energy = round(annual_kwh * electricity_rate, 2) if electricity_rate is not None else 0.0
    annual_support = _money(candidate.get("annual_support_cost")) or 0.0
    annual_software = _money(candidate.get("annual_software_cost")) or 0.0
    annual_maintenance = parameters["annual_maintenance_reserve"] + (
        _money(candidate.get("additional_annual_maintenance_cost")) or 0.0
    )
    annual_financial_cost = round(
        annual_energy + annual_support + annual_software + annual_maintenance,
        2,
    )

    downtime_hours = _number(candidate.get("expected_downtime_hours_per_year"))
    if downtime_hours is None:
        downtime_hours = parameters["expected_downtime_hours_per_year"]
    annual_downtime_exposure = round(
        downtime_hours * parameters["downtime_cost_per_hour"], 2
    )
    recurring_risk = 0.0
    one_time_risk = 0.0
    for risk in candidate.get("risk_events") or []:
        if not isinstance(risk, dict):
            continue
        expected_loss = (_number(risk.get("probability")) or 0.0) * (
            _money(risk.get("financial_impact")) or 0.0
        )
        if risk.get("frequency") == "annual":
            recurring_risk += expected_loss
        else:
            one_time_risk += expected_loss
    annual_risk_exposure = round(annual_downtime_exposure + recurring_risk, 2)

    residual_value = round(base_price * parameters["residual_value_percent"], 2)
    annuity_factor = _present_value_annuity_factor(discount_rate, horizon)
    discounted_residual = residual_value / ((1 + discount_rate) ** horizon)
    financial_npv = round(
        landed_acquisition + annual_financial_cost * annuity_factor - discounted_residual,
        2,
    )
    risk_adjusted_npv = round(
        financial_npv + annual_risk_exposure * annuity_factor + one_time_risk,
        2,
    )
    undiscounted = round(
        landed_acquisition + annual_financial_cost * horizon - residual_value,
        2,
    )
    productive_hours = parameters["active_hours_per_year"] * horizon
    return {
        "model_status": "partial_unpriced_items_remain"
        if candidate.get("open_cost_items") or not landed_cost_input_complete
        else "modeled_from_supplied_costs_and_assumptions",
        "landed_cost_input_complete": landed_cost_input_complete,
        "excluded_or_unpriced_costs": list(candidate.get("open_cost_items") or []),
        "base_purchase_price": base_price,
        "mandatory_options_cost": mandatory_options,
        "taxable_vendor_cost": taxable_vendor_cost,
        "sales_tax_estimate": sales_tax,
        "vendor_cash_cost": vendor_cash_cost,
        "internal_labor_hours": round(total_internal_hours, 2),
        "internal_implementation_cost": internal_implementation,
        "landed_acquisition_cost": landed_acquisition,
        "active_power_watts": round(active_power_watts, 2),
        "idle_power_watts": round(idle_power_watts, 2),
        "power_measurement_status": power.get("measurement_status"),
        "annual_energy_kwh": annual_kwh,
        "annual_energy_cost": annual_energy,
        "annual_maintenance_reserve": round(annual_maintenance, 2),
        "annual_support_and_software_cost": round(annual_support + annual_software, 2),
        "annual_financial_operating_cost": annual_financial_cost,
        "annual_downtime_exposure": annual_downtime_exposure,
        "annual_risk_exposure": annual_risk_exposure,
        "residual_value": residual_value,
        "undiscounted_lifecycle_cost": undiscounted,
        "financial_npv_tco": financial_npv,
        "risk_adjusted_npv_tco": risk_adjusted_npv,
        "equivalent_annual_cost": round(
            risk_adjusted_npv * _capital_recovery_factor(discount_rate, horizon), 2
        ),
        "financial_cost_per_productive_hour": round(financial_npv / productive_hours, 2)
        if productive_hours
        else None,
        "risk_adjusted_cost_per_productive_hour": round(
            risk_adjusted_npv / productive_hours, 2
        )
        if productive_hours
        else None,
    }


def _scenario_analysis(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, raw_scenario in enumerate(parameters.get("scenarios") or [], start=1):
        if not isinstance(raw_scenario, dict):
            continue
        scenario = dict(parameters)
        if "horizon_years" in raw_scenario:
            scenario["horizon_years"] = max(
                1, int(_number(raw_scenario["horizon_years"]) or 1)
            )
        for key in (
            "electricity_rate_per_kwh",
            "active_hours_per_year",
            "idle_hours_per_year",
            "loaded_labor_cost_per_hour",
            "downtime_cost_per_hour",
            "expected_downtime_hours_per_year",
            "annual_maintenance_reserve",
            "residual_value_percent",
        ):
            if key in raw_scenario:
                scenario[key] = _number(raw_scenario[key]) or 0.0
        for key in ("discount_rate", "tax_rate", "residual_value_percent"):
            if key in raw_scenario:
                scenario[key] = _rate(raw_scenario[key]) or 0.0
        metrics = _cost_metrics(candidate, scenario)
        results.append(
            {
                "name": str(raw_scenario.get("name") or f"scenario_{index}"),
                "financial_npv_tco": metrics["financial_npv_tco"],
                "risk_adjusted_npv_tco": metrics["risk_adjusted_npv_tco"],
                "equivalent_annual_cost": metrics["equivalent_annual_cost"],
                "annual_energy_cost": metrics["annual_energy_cost"],
                "annual_downtime_exposure": metrics["annual_downtime_exposure"],
                "residual_value": metrics["residual_value"],
            }
        )
    return results


def _acquisition_method_analysis(
    candidate: dict[str, Any], vendor_cash_cost: float, discount_rate: float
) -> list[dict[str, Any]]:
    methods = [
        {
            "method": "cash",
            "status": "modeled",
            "nominal_cash_outflow": vendor_cash_cost,
            "present_value_cost": vendor_cash_cost,
            "incremental_present_value_vs_cash": 0.0,
        }
    ]
    supplied_options = list(candidate.get("acquisition_methods") or [])
    supplied_method_names = {
        str(option.get("method") or "").strip().lower()
        for option in supplied_options
        if isinstance(option, dict)
    }
    if "finance" not in supplied_method_names:
        supplied_options.append(
            {
                "method": "finance",
                "missing_terms": [
                    "eligible amount",
                    "down payment",
                    "APR",
                    "term",
                    "fees",
                ],
            }
        )
    if "lease" not in supplied_method_names:
        supplied_options.append(
            {
                "method": "lease",
                "missing_terms": [
                    "monthly payment",
                    "term",
                    "upfront payment",
                    "fees",
                    "end-of-term return or buyout terms",
                ],
            }
        )
    for option in supplied_options:
        if not isinstance(option, dict):
            continue
        method = str(option.get("method") or "unknown").strip().lower()
        months = int(_number(option.get("term_months")) or 0)
        down_payment = _money(option.get("down_payment")) or 0.0
        fees = _money(option.get("fees")) or 0.0
        if method == "finance" and months and _rate(option.get("annual_percentage_rate")) is not None:
            principal = max(0.0, vendor_cash_cost - down_payment)
            monthly_rate = (_rate(option["annual_percentage_rate"]) or 0.0) / 12
            payment = (
                principal / months
                if monthly_rate == 0
                else principal
                * monthly_rate
                * (1 + monthly_rate) ** months
                / ((1 + monthly_rate) ** months - 1)
            )
            discount_monthly = discount_rate / 12
            pv_factor = _present_value_annuity_factor(discount_monthly, months)
            present_value_cost = round(
                down_payment + fees + payment * pv_factor, 2
            )
            methods.append(
                {
                    "method": method,
                    "status": "modeled",
                    "monthly_payment": round(payment, 2),
                    "nominal_cash_outflow": round(down_payment + fees + payment * months, 2),
                    "financing_cost": round(payment * months - principal + fees, 2),
                    "present_value_cost": present_value_cost,
                    "incremental_present_value_vs_cash": round(
                        present_value_cost - vendor_cash_cost, 2
                    ),
                }
            )
        elif method == "lease" and months and _money(option.get("monthly_payment")) is not None:
            payment = _money(option["monthly_payment"]) or 0.0
            buyout = _money(option.get("buyout_cost")) or 0.0
            discount_monthly = discount_rate / 12
            pv_factor = _present_value_annuity_factor(discount_monthly, months)
            present_value_cost = round(
                down_payment
                + fees
                + payment * pv_factor
                + buyout / ((1 + discount_monthly) ** months),
                2,
            )
            methods.append(
                {
                    "method": method,
                    "status": "modeled",
                    "monthly_payment": payment,
                    "nominal_cash_outflow": round(down_payment + fees + payment * months + buyout, 2),
                    "present_value_cost": present_value_cost,
                    "incremental_present_value_vs_cash": round(
                        present_value_cost - vendor_cash_cost, 2
                    ),
                }
            )
        else:
            methods.append(
                {
                    "method": method,
                    "status": "not_modeled_missing_terms",
                    "missing_terms": list(option.get("missing_terms") or []),
                }
            )
    return methods


def _build_commercial_candidate_comparisons(
    inputs: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    parameters = _analysis_parameters(inputs)
    comparisons: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        metrics = _cost_metrics(candidate, parameters)
        hard_checks = _commercial_constraint_checks(
            inputs, candidate, metrics["landed_acquisition_cost"]
        )
        hard_checks["landed_cost_inputs_present"] = bool(
            metrics["landed_cost_input_complete"]
        )
        source_urls = [candidate.get("source_url")]
        source_urls.extend(
            item.get("source_url")
            for item in candidate.get("mandatory_options") or []
            if isinstance(item, dict)
        )
        source_urls.extend((candidate.get("power_model") or {}).get("source_urls") or [])
        source_urls.extend(parameters.get("source_refs") or [])
        source_urls = list(dict.fromkeys(url for url in source_urls if url))
        comparisons.append(
            {
                "candidate_id": str(candidate.get("candidate_id") or f"candidate_{index}"),
                "label": str(candidate.get("name") or candidate.get("model") or f"Candidate {index}"),
                "vendor": candidate.get("vendor"),
                "source_ref": candidate.get("source_ref"),
                "source_url": candidate.get("source_url"),
                "source_urls": source_urls,
                "source_type": candidate.get("source_type"),
                "observed_at": candidate.get("observed_at") or candidate.get("quote_date"),
                "availability_status": candidate.get("availability_status"),
                "available_for_purchase": candidate.get("available_for_purchase"),
                "quote_valid_until": candidate.get("quote_valid_until"),
                "lead_time_business_days": _number(candidate.get("lead_time_business_days")),
                "quote_subtotal": metrics["base_purchase_price"],
                "sales_tax_estimate": metrics["sales_tax_estimate"],
                "known_upfront_cost": metrics["landed_acquisition_cost"],
                "known_three_year_cost": metrics["undiscounted_lifecycle_cost"],
                "tco": metrics,
                "scenario_analysis": _scenario_analysis(candidate, parameters),
                "acquisition_method_analysis": _acquisition_method_analysis(
                    candidate, metrics["vendor_cash_cost"], parameters["discount_rate"]
                ),
                "tco_methodology": {
                    "horizon_years": parameters["horizon_years"],
                    "discount_rate": parameters["discount_rate"],
                    "tax_rate": parameters["tax_rate"],
                    "electricity_rate_per_kwh": parameters["electricity_rate_per_kwh"],
                    "active_hours_per_year": parameters["active_hours_per_year"],
                    "idle_hours_per_year": parameters["idle_hours_per_year"],
                    "loaded_labor_cost_per_hour": parameters["loaded_labor_cost_per_hour"],
                    "downtime_cost_per_hour": parameters["downtime_cost_per_hour"],
                    "expected_downtime_hours_per_year": parameters["expected_downtime_hours_per_year"],
                    "annual_maintenance_reserve": parameters["annual_maintenance_reserve"],
                    "residual_value_percent": parameters["residual_value_percent"],
                    "methods": [
                        "landed acquisition cost",
                        "discounted lifecycle cost (NPV TCO)",
                        "risk-adjusted NPV including downtime exposure",
                        "equivalent annual cost",
                        "cost per productive hour",
                        "cash-versus-finance-versus-lease comparison when terms are supplied",
                        "scenario sensitivity",
                    ],
                },
                "hard_constraint_checks": hard_checks,
                "hard_constraints_passed": all(hard_checks.values()),
                "specifications": dict(candidate.get("specifications") or {}),
                "warranty_years": _number(_candidate_value(candidate, "min_warranty_years")),
                "commercial_terms": dict(candidate.get("commercial_terms") or {}),
                "disclosures": list(candidate.get("disclosures") or []),
                "unknown_costs": list(candidate.get("open_cost_items") or []),
            }
        )
    comparisons.sort(
        key=lambda item: (
            not item["hard_constraints_passed"],
            item["tco"]["risk_adjusted_npv_tco"],
            item["candidate_id"],
        )
    )
    return comparisons


def build_candidate_comparisons(
    inputs: dict[str, Any], documents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates = _candidate_records(documents)
    if inputs.get("purchase_type") not in {"property", "rental_property"}:
        return _build_commercial_candidate_comparisons(inputs, candidates)
    comparisons: list[dict[str, Any]] = []
    constraints = inputs.get("constraints") or {}
    for index, candidate in enumerate(candidates, start=1):
        asking = _money(candidate.get("asking_price"))
        closing = _money(candidate.get("closing_cost_estimate"))
        inspection = _money(candidate.get("inspection_reserve"))
        tax = _money(candidate.get("annual_property_tax"))
        insurance = _money(candidate.get("annual_insurance_estimate"))
        hoa = _money(candidate.get("hoa_monthly")) or 0.0
        known_upfront = round(sum(value or 0.0 for value in (asking, closing, inspection)), 2)
        known_annual = round(sum(value or 0.0 for value in (tax, insurance)) + hoa * 12, 2)
        hard_checks = {
            "property_type": not constraints.get("property_type") or str(candidate.get("property_type") or "").lower() == str(constraints.get("property_type") or "").lower(),
            "min_bedrooms": not constraints.get("min_bedrooms") or int(candidate.get("bedrooms") or 0) >= int(constraints.get("min_bedrooms") or 0),
            "zip_code": not constraints.get("zip_code") or str(candidate.get("zip_code") or "") == str(constraints.get("zip_code") or ""),
            "budget": inputs.get("budget") in (None, "") or (asking is not None and asking <= float(inputs["budget"])),
        }
        comparisons.append(
            {
                "candidate_id": str(candidate.get("candidate_id") or f"candidate_{index}"),
                "label": str(candidate.get("address") or candidate.get("name") or f"Candidate {index}"),
                "source_ref": candidate.get("source_ref"),
                "observed_at": candidate.get("observed_at"),
                "asking_price": asking,
                "known_upfront_cost": known_upfront,
                "known_annual_carry": known_annual,
                "known_five_year_cost_before_financing_utilities_and_resale": round(known_upfront + known_annual * 5, 2),
                "hard_constraint_checks": hard_checks,
                "hard_constraints_passed": all(hard_checks.values()),
                "condition": candidate.get("condition"),
                "disclosures": list(candidate.get("disclosures") or []),
                "unknown_costs": ["financing interest", "utilities", "maintenance beyond disclosed reserve", "transaction-specific legal and title costs", "resale proceeds"],
            }
        )
    comparisons.sort(
        key=lambda item: (
            not item["hard_constraints_passed"],
            item["known_five_year_cost_before_financing_utilities_and_resale"],
            item["candidate_id"],
        )
    )
    return comparisons


def analyze_total_cost(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = _state(ctx)
    inputs = state.get("inputs") or _inputs(ctx)
    comparisons = build_candidate_comparisons(inputs, state.get("documents") or [])
    state["candidate_comparisons"] = comparisons
    if inputs.get("purchase_type") not in {"property", "rental_property"} and comparisons:
        evidence = dict(state.get("evidence") or {})
        evidence["observed_price_values"] = [
            item["known_upfront_cost"]
            for item in comparisons
            if item.get("known_upfront_cost") is not None
        ]
        evidence["price_evidence_label"] = "Modeled landed acquisition costs"
        evidence["market_source_urls"] = list(
            dict.fromkeys(
                url
                for item in comparisons
                for url in item.get("source_urls") or []
                if url
            )
        )
        state["evidence"] = evidence
    settings = analysis_settings(ctx["config"])
    candidate_packet, metrics = candidate_analysis_packet(
        comparisons, max_candidates=settings["max_candidates"]
    )
    source_refs = sorted(known_source_refs(state))[: settings["max_list_items"]]
    payload = {
        "purchase": {
            "purchase_type": inputs.get("purchase_type"),
            "item_description": inputs.get("item_description"),
            "budget": inputs.get("budget"),
            "priorities": inputs.get("priorities") or [],
            "constraints": inputs.get("constraints") or {},
        },
        "analysis_assumptions": inputs.get("analysis") or {},
        "candidate_results": candidate_packet,
        "authoritative_metrics": metrics,
        "allowed_source_refs": source_refs,
        "authority": {
            "deterministic_values_immutable": True,
            "ranking_immutable": True,
            "narrative_must_use_metric_refs": True,
        },
    }
    primary_cost_drivers = []
    scenario_insights = []
    acquisition_tradeoffs = []
    for candidate in candidate_packet:
        candidate_id = candidate["candidate_id"]
        metric_refs = list(candidate.get("metrics") or {})
        if metric_refs:
            primary_cost_drivers.append(
                {
                    "candidate_id": candidate_id,
                    "metric_refs": metric_refs[:2],
                    "explanation": "The deterministic lifecycle model identifies acquisition and recurring ownership costs as the decision basis.",
                }
            )
        if candidate.get("scenarios"):
            scenario_insights.append(
                {
                    "candidate_id": candidate_id,
                    "scenario_name": "modeled scenario range",
                    "metric_refs": [
                        ref
                        for scenario in candidate["scenarios"]
                        for ref in scenario.get("metric_refs") or []
                    ][:2],
                    "interpretation": "The modeled scenarios show that operating assumptions can materially change lifecycle exposure.",
                }
            )
        for method in candidate.get("acquisition_methods") or []:
            acquisition_tradeoffs.append(
                {
                    "candidate_id": candidate_id,
                    "method": method.get("method") or "unknown",
                    "status": "Use the deterministic method status and complete missing commercial terms before comparison.",
                    "metric_refs": list(method.get("metric_refs") or [])[:2],
                    "interpretation": "Funding structure is comparable only when complete transaction terms are available.",
                }
            )
    fallback = {
        "summary": "Deterministic lifecycle economics were calculated for the supplied options; the tables remain authoritative and require human review.",
        "primary_cost_drivers": primary_cost_drivers[: settings["max_list_items"]],
        "scenario_insights": scenario_insights[: settings["max_list_items"]],
        "assumption_sensitivities": [
            {
                "candidate_id": "",
                "assumption_key": str(key),
                "direction": "requires approved company input",
                "why": "This planning assumption can change lifecycle economics without changing observed supplier facts.",
                "verification_needed": "Replace the planning value with an approved business assumption before commitment.",
                "metric_refs": [],
            }
            for key in list((inputs.get("analysis") or {}))[: settings["max_list_items"]]
            if key not in {"source_refs", "scenarios"}
        ],
        "acquisition_method_tradeoffs": acquisition_tradeoffs[: settings["max_list_items"]],
        "evidence_gaps": list(state.get("evidence_gaps") or []),
        "source_refs": [],
        **analysis_validation_context(state, payload),
        "_metric_refs": sorted(metrics),
    }
    state["analysis_interpretation"] = generate_structured_analysis(
        state=state,
        config=ctx["config"],
        agent_id="purchase_total_cost_analyst",
        prompt_name="purchase-tco-analysis-task.md",
        payload={
            **payload,
            "output_contract": {
                "summary": "string",
                "primary_cost_drivers": "list of candidate_id, metric_refs, explanation",
                "scenario_insights": "list of candidate_id, scenario_name, metric_refs, interpretation",
                "assumption_sensitivities": "list of assumption_key, direction, why, verification_needed, metric_refs",
                "acquisition_method_tradeoffs": "list of candidate_id, method, status, metric_refs, interpretation",
                "evidence_gaps": "list of strings",
                "source_refs": "list drawn from allowed_source_refs",
            },
        },
        fallback=fallback,
        validator=validate_tco_analysis,
        llm_client=llm_client,
    )
    _save(ctx, state)
    return {"candidate_count": len(comparisons), "constraint_match_count": sum(1 for item in comparisons if item["hard_constraints_passed"])}


def build_purchase_risk_review(
    comparisons: list[dict[str, Any]], purchase_type: str = "custom"
) -> dict[str, list[str]]:
    if purchase_type not in {"property", "rental_property"}:
        return _build_commercial_risk_review(comparisons)
    risk_flags: list[str] = []
    if not comparisons:
        risk_flags.append("No structured candidate records were available for comparison.")
    if comparisons and not any(item.get("hard_constraints_passed") for item in comparisons):
        risk_flags.append("No candidate satisfies every declared hard constraint.")
    for item in comparisons:
        if item.get("disclosures"):
            risk_flags.append(f"{item['candidate_id']}: disclosed condition items require qualified inspection and cost validation.")
        if not item.get("observed_at"):
            risk_flags.append(f"{item['candidate_id']}: listing observation date is missing.")
    evidence_gaps = [
        "Verify that the listing is active and the asking price has not changed.",
        "Obtain an independent inspection and specialist quotes for disclosed defects.",
        "Confirm taxes, insurability, title, zoning, utilities, and any association obligations.",
        "Model financing, cash-to-close, maintenance, and downside resale scenarios using customer-specific terms.",
    ]
    return {
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "evidence_gaps": evidence_gaps,
    }


def _build_commercial_risk_review(
    comparisons: list[dict[str, Any]],
) -> dict[str, list[str]]:
    risk_flags: list[str] = []
    if not comparisons:
        risk_flags.append("No structured, source-backed market observations were available for comparison.")
    if comparisons and not any(item.get("hard_constraints_passed") for item in comparisons):
        risk_flags.append("No observed option satisfies every declared technical, availability, warranty, and landed-cost constraint.")
    for item in comparisons:
        if item.get("disclosures"):
            risk_flags.append(
                f"{item['candidate_id']}: listing disclosures or planning qualifications require procurement and technical-owner review."
            )
        if not item.get("observed_at"):
            risk_flags.append(f"{item['candidate_id']}: market-observation timestamp is missing.")
        if not item.get("source_url"):
            risk_flags.append(f"{item['candidate_id']}: supplier source URL is missing.")
        if not item.get("availability_status"):
            risk_flags.append(f"{item['candidate_id']}: availability status is missing.")
        if item.get("available_for_purchase") is not True:
            risk_flags.append(
                f"{item['candidate_id']}: the observed listing does not establish current purchase availability."
            )
        if item.get("source_type") in {
            "public_retail_listing",
            "manufacturer_store_listing",
            "authorized_retailer_listing",
        }:
            risk_flags.append(
                f"{item['candidate_id']}: public price and stock are observations, not a reserved quote; refresh at approval time."
            )
    return {
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "evidence_gaps": [
            "Refresh price, stock, configuration, tax, delivery or pickup, and return terms; then obtain a written business quote before issuing a purchase order.",
            "Obtain written confirmation of the exact GPU, VRAM, memory, storage, power supply, operating system, warranty, and support configuration.",
            "Replace loaded labor, utilization, downtime, maintenance, discount-rate, and residual-value planning assumptions with approved company inputs.",
            "Measure or benchmark wall-power consumption under the intended workload and validate security, network, electrical, cooling, software-license, and deployment readiness.",
            "Obtain complete APR, fee, term, security-interest, early-payoff, lease-return, and buyout terms before comparing financing or leasing with cash purchase.",
        ],
    }


def review_purchase_risks(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = _state(ctx)
    inputs = state.get("inputs") or _inputs(ctx)
    review = build_purchase_risk_review(
        state.get("candidate_comparisons") or [], inputs.get("purchase_type") or "custom"
    )
    state.update(review)
    settings = analysis_settings(ctx["config"])
    comparisons = state.get("candidate_comparisons") or []
    candidate_packet, metrics = candidate_analysis_packet(
        comparisons, max_candidates=settings["max_candidates"]
    )
    candidate_ids = {
        str(item.get("candidate_id"))
        for item in comparisons
        if isinstance(item, dict) and item.get("candidate_id")
    }
    material_risks = []
    for risk in review["risk_flags"][: settings["max_list_items"]]:
        prefix = str(risk).split(":", 1)[0]
        candidate_id = prefix if prefix in candidate_ids else ""
        material_risks.append(
            {
                "candidate_id": candidate_id,
                "category": "procurement verification",
                "severity": "high" if candidate_id else "moderate",
                "reason": str(risk),
                "mitigation": "Resolve the deterministic evidence gap before making a commitment.",
                "owner_role": "Procurement owner",
                "blocks_commitment": True,
                "evidence_refs": [],
            }
        )
    eligible = [item for item in comparisons if item.get("hard_constraints_passed")]
    payload = {
        "purchase": {
            "purchase_type": inputs.get("purchase_type"),
            "item_description": inputs.get("item_description"),
            "constraints": inputs.get("constraints") or {},
            "priorities": inputs.get("priorities") or [],
        },
        "candidate_results": candidate_packet,
        "authoritative_metrics": metrics,
        "deterministic_risk_flags": review["risk_flags"],
        "deterministic_evidence_gaps": review["evidence_gaps"],
        "allowed_source_refs": sorted(known_source_refs(state))[: settings["max_list_items"]],
        "authority": {
            "hard_gates_immutable": True,
            "risk_flags_immutable": True,
            "narrative_only": True,
        },
    }
    fallback = {
        "overall_posture": "high" if not eligible else "moderate" if review["risk_flags"] else "low",
        "material_risks": material_risks,
        "deal_breakers": [
            "No observed option passes every declared hard constraint."
        ]
        if comparisons and not eligible
        else [],
        "negotiation_points": list(review["evidence_gaps"])[: settings["max_list_items"]],
        "verification_plan": list(review["evidence_gaps"])[: settings["max_list_items"]],
        "source_refs": [],
        **analysis_validation_context(state, payload),
    }
    state["risk_interpretation"] = generate_structured_analysis(
        state=state,
        config=ctx["config"],
        agent_id="purchase_risk_reviewer",
        prompt_name="purchase-risk-analysis-task.md",
        payload={
            **payload,
            "output_contract": {
                "overall_posture": "low, moderate, high, or indeterminate",
                "material_risks": "list of candidate_id, category, severity, reason, mitigation, owner_role, blocks_commitment, evidence_refs",
                "deal_breakers": "list of strings",
                "negotiation_points": "list of strings",
                "verification_plan": "list of strings",
                "source_refs": "list drawn from allowed_source_refs",
            },
        },
        fallback=fallback,
        validator=validate_risk_analysis,
        llm_client=llm_client,
    )
    _save(ctx, state)
    return {"risk_count": len(review["risk_flags"]), "evidence_gap_count": len(review["evidence_gaps"])}


def audit_recommendation(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    state = _state(ctx)
    inputs = state.get("inputs") or _inputs(ctx)
    sources = state.get("sources") or []
    evidence = state.get("evidence") or deterministic_evidence(inputs, state.get("documents") or [], sources)
    deterministic = deterministic_recommendation(evidence, sources)
    comparisons = state.get("candidate_comparisons") or []
    eligible = [item for item in comparisons if item.get("hard_constraints_passed")]
    if eligible:
        deterministic = {
            "label": "consider",
            "confidence": "low" if not any(item.get("status") == "observed" for item in sources) else "medium",
            "rationale": "At least one source-backed market option satisfies the declared availability, technical, warranty, and landed-cost gates. Eligible options are ranked by risk-adjusted discounted TCO, but public price and stock, company cost assumptions, exact configuration, supplier terms, and deployment readiness still require validation.",
        }
    preferred = eligible[0] if eligible else None
    recommendation = dict(deterministic)
    recommendation.update(
        {
            "preferred_candidate": preferred.get("candidate_id") if preferred else None,
            "risk_flags": state.get("risk_flags") or [],
            "evidence_gaps": state.get("evidence_gaps") or [],
        }
    )
    settings = analysis_settings(ctx["config"])
    candidate_packet, metrics = candidate_analysis_packet(
        comparisons, max_candidates=settings["max_candidates"]
    )
    payload = {
        "purchase": {
            "purchase_type": inputs.get("purchase_type"),
            "item_description": inputs.get("item_description"),
            "budget": inputs.get("budget"),
            "priorities": inputs.get("priorities") or [],
            "constraints": inputs.get("constraints") or {},
        },
        "candidate_results": candidate_packet,
        "authoritative_metrics": metrics,
        "deterministic_recommendation": recommendation,
        "analysis_interpretation": state.get("analysis_interpretation") or {},
        "risk_interpretation": state.get("risk_interpretation") or {},
        "deterministic_risk_flags": state.get("risk_flags") or [],
        "deterministic_evidence_gaps": state.get("evidence_gaps") or [],
        "allowed_source_refs": sorted(known_source_refs(state))[: settings["max_list_items"]],
        "authority": {
            "preferred_candidate_immutable": True,
            "recommendation_label_immutable": True,
            "confidence_immutable": True,
            "ranking_immutable": True,
        },
    }
    why_not = []
    for candidate in comparisons:
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id or candidate_id == recommendation.get("preferred_candidate"):
            continue
        explanation = (
            "This option fails one or more deterministic hard constraints."
            if not candidate.get("hard_constraints_passed")
            else "The deterministic lifecycle ranking placed this eligible option below the preferred option."
        )
        why_not.append({"candidate_id": candidate_id, "explanation": explanation})
    fallback = {
        "why_preferred": deterministic["rationale"],
        "why_not_alternatives": why_not[: settings["max_list_items"]],
        "strongest_reason_to_proceed": "An eligible option is available for further procurement validation." if preferred else "No option is ready to proceed.",
        "strongest_reason_to_wait": (state.get("evidence_gaps") or ["Complete the outstanding procurement verification before commitment."])[0],
        "approval_conditions": list(state.get("evidence_gaps") or [])[: settings["max_list_items"]],
        "confidence_explanation": "Confidence remains bounded by source freshness, evidence completeness, and required human approval.",
        "source_refs": [],
        **analysis_validation_context(state, payload),
    }
    decision_analysis = generate_structured_analysis(
        state=state,
        config=ctx["config"],
        agent_id="purchase_recommendation_auditor",
        prompt_name="purchase-decision-analysis-task.md",
        payload={
            **payload,
            "output_contract": {
                "why_preferred": "string",
                "why_not_alternatives": "list of candidate_id and explanation",
                "strongest_reason_to_proceed": "string",
                "strongest_reason_to_wait": "string",
                "approval_conditions": "list of strings",
                "confidence_explanation": "string",
                "source_refs": "list drawn from allowed_source_refs",
            },
        },
        fallback=fallback,
        validator=validate_decision_analysis,
        llm_client=llm_client,
    )
    state["decision_analysis"] = decision_analysis
    actor_id = "purchase_recommendation_auditor"
    actor_spec = resolve_actor_specs(ctx["config"], actor_ids=[actor_id]).get(actor_id) or {}
    phase = ((state.get("llm_generation") or {}).get("phases") or {}).get(actor_id) or {}
    actor_findings = dict(state.get("actor_findings") or {})
    actor_findings[actor_id] = {
        "actor_id": actor_id,
        "role": actor_spec.get("role") or "Procurement Recommendation Auditor",
        "summary": decision_analysis.get("why_preferred"),
        "findings": decision_analysis.get("approval_conditions") or [],
        "risks": [decision_analysis.get("strongest_reason_to_wait")],
        "recommended_next_step": (decision_analysis.get("approval_conditions") or ["Human review required."])[0],
        "provider": phase.get("provider") or "deterministic_fallback",
        "model": phase.get("model") or "deterministic",
        "confidence": recommendation.get("confidence"),
        "source_refs": decision_analysis.get("source_refs") or [],
    }
    state.update(
        {
            "inputs": inputs,
            "evidence": evidence,
            "recommendation": recommendation,
            "actor_findings": actor_findings,
        }
    )
    _save(ctx, state)
    return {"recommended_action": recommendation["label"], "preferred_candidate": recommendation.get("preferred_candidate")}
