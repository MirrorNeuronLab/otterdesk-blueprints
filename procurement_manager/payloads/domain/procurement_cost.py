"""Deterministic, quote-backed procurement cash-flow calculations."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def money(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("a quoted amount is required")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid quoted amount") from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValueError("amount must be finite, nonnegative, and in minor units")
    return amount


def _display(amount: Decimal) -> str:
    return f"{amount:.2f}"


def model_cost(quote: dict[str, Any], horizon_months: int) -> dict[str, Any]:
    """Return known costs without treating missing quote fields as zero."""
    if not 1 <= horizon_months <= 120:
        raise ValueError("comparison horizon must be 1 to 120 months")
    currency = quote.get("currency")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError("a three-letter quote currency is required")
    unknown: list[str] = []
    flows: list[dict[str, Any]] = []
    quantity = quote.get("quantity")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise ValueError("quote quantity must be a positive integer")
    if quote.get("unit_price") is None:
        unknown.append("unit_price")
        hardware = Decimal(0)
    else:
        hardware = money(quote["unit_price"]) * quantity
        flows.append({"month": 0, "kind": "hardware", "amount": _display(hardware)})
    for kind in ("shipping", "tax"):
        if quote.get(kind) is None:
            unknown.append(kind)
        else:
            flows.append({"month": 0, "kind": kind, "amount": _display(money(quote[kind]))})
    support = quote.get("required_support")
    if support is None:
        unknown.append("required_support")
    elif support.get("included"):
        if support.get("payments"):
            raise ValueError("included support cannot have incremental payments")
    else:
        for payment in support.get("payments", []):
            month = payment.get("month")
            if not isinstance(month, int) or month < 0:
                raise ValueError("support payment month must be nonnegative")
            flows.append({"month": month, "kind": "required_support", "amount": _display(money(payment.get("amount")))})
    cash = sum((Decimal(flow["amount"]) for flow in flows if flow["month"] == 0), Decimal(0))
    horizon = sum((Decimal(flow["amount"]) for flow in flows if flow["month"] < horizon_months), Decimal(0))
    commitment = sum((Decimal(flow["amount"]) for flow in flows), Decimal(0))
    return {
        "currency": currency.upper(), "horizon_months": horizon_months,
        "cash_due_at_order": None if any(k in unknown for k in ("unit_price", "shipping", "tax", "required_support")) else _display(cash),
        "known_contractual_commitment": None if "unit_price" in unknown else _display(commitment),
        "known_cost_over_comparison_horizon": None if "unit_price" in unknown else _display(horizon),
        "unknown_or_unquantified_cost_items": unknown + ["energy", "resale_value", "downtime"],
        "cash_flows": flows,
        "label": "Known cost subtotal over the comparison horizon",
    }
