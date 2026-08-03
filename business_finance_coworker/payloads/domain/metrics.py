from __future__ import annotations

import math
from typing import Any

from .common import as_number, round_or_none


def calculate_unit_economics(metrics: dict[str, Any]) -> dict[str, Any]:
    visitors = as_number(metrics.get("monthly_qualified_visitors"))
    signups = as_number(metrics.get("monthly_signups"))
    activated = _first_number(metrics, "monthly_activated_customers", "monthly_activated_families")
    trials = _first_number(metrics, "monthly_trial_customers", "monthly_trial_families")
    new_paid = _first_number(metrics, "monthly_new_paid_customers", "monthly_new_paid_families")
    paying = _first_number(metrics, "paying_customers_end_of_period", "paying_families_end_of_period")
    arpu = as_number(metrics.get("monthly_arpu"))
    margin = as_number(metrics.get("gross_margin_rate"))
    churn = as_number(metrics.get("monthly_churn_rate"))
    spend = as_number(metrics.get("monthly_acquisition_spend"))
    fixed = as_number(metrics.get("monthly_fixed_operating_costs"))

    monthly_revenue = _product(paying, arpu)
    monthly_gross_profit = _product(monthly_revenue, margin)
    monthly_contribution = _subtract(monthly_gross_profit, spend, fixed)
    cac = _divide(spend, new_paid)
    gross_profit_per_customer = _product(arpu, margin)
    ltv = _divide(gross_profit_per_customer, churn)
    payback = _divide(cac, gross_profit_per_customer)
    break_even = None
    if gross_profit_per_customer and gross_profit_per_customer > 0 and spend is not None and fixed is not None:
        break_even = math.ceil((spend + fixed) / gross_profit_per_customer)

    values = {
        "visitor_to_signup_rate": _divide(signups, visitors),
        "signup_to_activation_rate": _divide(activated, signups),
        "activation_to_trial_rate": _divide(trials, activated),
        "trial_to_paid_rate": _divide(new_paid, trials),
        "monthly_revenue": monthly_revenue,
        "monthly_gross_profit": monthly_gross_profit,
        "monthly_contribution_after_fixed_costs_and_acquisition": monthly_contribution,
        "blended_cac": cac,
        "modeled_gross_profit_ltv": ltv,
        "modeled_cac_payback_months": payback,
        "break_even_paying_customers": break_even,
        "current_paying_customers": paying,
        "monthly_churn_rate": churn,
        "gross_margin_rate": margin,
    }
    missing = [
        name
        for name, value in {
            "monthly_qualified_visitors": visitors,
            "monthly_signups": signups,
            "monthly_activated_customers": activated,
            "monthly_trial_customers": trials,
            "monthly_new_paid_customers": new_paid,
            "paying_customers_end_of_period": paying,
            "monthly_arpu": arpu,
            "gross_margin_rate": margin,
            "monthly_churn_rate": churn,
            "monthly_acquisition_spend": spend,
            "monthly_fixed_operating_costs": fixed,
        }.items()
        if value is None
    ]
    return {
        "status": "observed_inputs_modeled_outputs" if not missing else "incomplete",
        "currency": str(metrics.get("currency") or "not_reported"),
        "coverage_period": str(metrics.get("coverage_period") or "not_reported"),
        "metrics": {key: round_or_none(value) for key, value in values.items()},
        "missing_inputs": missing,
        "formula_notes": [
            "Monthly revenue = paying customers × monthly ARPU.",
            "Contribution = revenue × gross margin rate − acquisition spend − fixed operating costs.",
            "Modeled LTV = monthly ARPU × gross margin rate ÷ monthly churn rate.",
            "CAC and LTV are directional when attribution and retention history are incomplete.",
        ],
    }


def _first_number(metrics: dict[str, Any], primary: str, demo_field: str) -> float | None:
    """Prefer the generic field while keeping the unchanged Bibblio demo readable."""
    value = metrics.get(primary)
    return as_number(value if value not in (None, "") else metrics.get(demo_field))


def _divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _product(*values: float | None) -> float | None:
    if any(value is None for value in values):
        return None
    result = 1.0
    for value in values:
        result *= float(value)
    return result


def _subtract(base: float | None, *values: float | None) -> float | None:
    if base is None or any(value is None for value in values):
        return None
    return float(base) - sum(float(value) for value in values)
