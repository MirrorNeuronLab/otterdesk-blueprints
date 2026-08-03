from __future__ import annotations

from typing import Any

from .collaboration import build_packet, peer_signals, persist_packet, write_final_artifact
from .inputs import json_object, resolve_input_file, source_descriptor
from .metrics import calculate_unit_economics


def run_finance_controller(context: dict[str, Any], *, step_id: str, **_: Any) -> dict[str, Any]:
    if step_id == "calculate_unit_economics":
        return _calculate_economics(context)
    if step_id == "publish_financial_control_packet":
        return _publish_finance_packet(context)
    raise ValueError(f"Finance co-worker does not own step {step_id!r}")


def _dataset(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], bool]:
    path = resolve_input_file(context, "metrics_file", "business_metrics.json")
    metrics = json_object(path)
    synthetic = str(metrics.get("data_status") or "").lower() == "synthetic_demo"
    return metrics, source_descriptor(path, synthetic=synthetic), synthetic


def _calculate_economics(context: dict[str, Any]) -> dict[str, Any]:
    metrics, source, synthetic = _dataset(context)
    economics = calculate_unit_economics(metrics)
    values = economics["metrics"]
    peers = peer_signals(context)
    packet = build_packet(
        context,
        stage="calculate_unit_economics",
        objective="Establish Bibblio's contribution economics, acquisition affordability, and break-even evidence gaps.",
        trigger="Founder supplies a dated subscription, spend, margin, and operating-cost snapshot.",
        sources=[source],
        observed_facts=[
            f"Supplied paying families: {_number(values.get('current_paying_families'))}.",
            f"Modeled monthly revenue: {_money(values.get('monthly_revenue'), economics['currency'])}.",
            f"Modeled monthly contribution after supplied fixed costs and acquisition: {_money(values.get('monthly_contribution_after_fixed_costs_and_acquisition'), economics['currency'])}.",
            f"Modeled break-even paying families: {_number(values.get('break_even_paying_families'))}.",
        ],
        assumptions=[
            "The supplied gross-margin rate includes all relevant variable inference, media, payment, and support costs.",
            "Founder time, tax, working capital, and unreported liabilities are excluded unless supplied.",
        ],
        analysis={
            "unit_economics": economics,
            "peer_goal_packet_count": len(peers["signals"]),
            "peer_goal_signals": peers["signals"],
            "decision_rule": "Do not scale acquisition until retained paid-family contribution is positive under the approved cash guardrail.",
        },
        recommendation="Protect cash and improve retained activation before scaling paid acquisition; replace every missing or synthetic input before a live budget decision.",
        confidence="low" if synthetic or economics["missing_inputs"] else "medium",
        risks=["Short retention history can overstate LTV.", "Blended CAC can hide weak channel quality.", "This is decision support, not accounting or tax advice."],
        requested_approval=["Founder, bookkeeper, or accountant confirms source coverage, cost allocation, cash, and liabilities."],
        outputs=["unit economics baseline", "break-even model", "financial evidence-gap register"],
        next_check="At the next complete month close or after material pricing, cost, or cohort changes.",
    )
    return persist_packet(context, packet)


def _publish_finance_packet(context: dict[str, Any]) -> dict[str, Any]:
    metrics, source, synthetic = _dataset(context)
    economics = calculate_unit_economics(metrics)
    values = economics["metrics"]
    contribution = values.get("monthly_contribution_after_fixed_costs_and_acquisition")
    packet = build_packet(
        context,
        stage="publish_financial_control_packet",
        objective="Publish an approval-ready financial control packet for Bibblio's profitability goal.",
        trigger="The deterministic unit-economics calculation is complete.",
        sources=[source],
        observed_facts=[
            f"Modeled monthly contribution is {_money(contribution, economics['currency'])}.",
            f"The calculation has {len(economics['missing_inputs'])} missing required inputs.",
        ],
        assumptions=economics["formula_notes"],
        analysis={"unit_economics": economics, "financial_status": "review_required"},
        recommendation="Approve only cash-bounded tests, refresh the model with observed cohort data, and defer paid-channel scaling until contribution and payback are defensible.",
        confidence="low" if synthetic or economics["missing_inputs"] else "medium",
        risks=["Synthetic or incomplete inputs cannot authorize spend or pricing changes.", "A positive modeled contribution does not replace reconciliation."],
        requested_approval=["Founder approves the operating cash guardrail; a qualified human approves accounting, tax, payment, pricing, and contract actions."],
        outputs=["financial control packet", "approval queue"],
        next_check="Weekly financial pulse and monthly close.",
        publication_state="final",
    )
    persisted = persist_packet(context, packet)
    final = write_final_artifact(
        context,
        packet,
        artifact_type="bibblio_financial_control_packet",
        executive_summary="The finance co-worker calculated contribution economics from supplied inputs and converted uncertainty into explicit cash and approval guardrails.",
        evidence={"unit_economics": economics, "model_status": "synthetic_demo" if synthetic else economics["status"]},
        next_steps=[
            "Replace synthetic inputs with reconciled billing, cost, cash, refund, and cohort exports.",
            "Confirm which direct content and support costs are included in gross margin.",
            "Set a founder-approved experiment cash limit.",
            "Share only finance thresholds and aggregate results with peer co-workers through MCP.",
        ],
        data_status="synthetic_demo" if synthetic else economics["status"],
    )
    return {**persisted, **final}


def _money(value: Any, currency: str) -> str:
    return "not reported" if not isinstance(value, (int, float)) else f"{currency} {float(value):,.2f}"


def _number(value: Any) -> str:
    return "not reported" if not isinstance(value, (int, float)) else f"{float(value):,.0f}"
