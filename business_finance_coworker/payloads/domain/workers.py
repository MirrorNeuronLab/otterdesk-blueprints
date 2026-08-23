from __future__ import annotations

from typing import Any

from .collaboration import build_packet, persist_packet, write_final_artifact
from .inputs import json_object, normalized_inputs, resolve_input_file, source_descriptor
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
    business_name = str(normalized_inputs(context)["business_name"])
    metrics, source, synthetic = _dataset(context)
    economics = calculate_unit_economics(metrics)
    values = economics["metrics"]
    packet = build_packet(
        context,
        stage="calculate_unit_economics",
        objective=f"Establish {business_name}'s contribution economics, acquisition affordability, and break-even evidence gaps.",
        trigger="Founder supplies a dated subscription, spend, margin, and operating-cost snapshot.",
        sources=[source],
        observed_facts=[
            f"Supplied paying customers: {_number(values.get('current_paying_customers'))}.",
            f"Modeled monthly revenue: {_money(values.get('monthly_revenue'), economics['currency'])}.",
            f"Modeled monthly contribution after supplied fixed costs and acquisition: {_money(values.get('monthly_contribution_after_fixed_costs_and_acquisition'), economics['currency'])}.",
            f"Modeled break-even paying customers: {_number(values.get('break_even_paying_customers'))}.",
        ],
        assumptions=[
            "The supplied gross-margin rate includes all relevant variable inference, media, payment, and support costs.",
            "Founder time, tax, working capital, and unreported liabilities are excluded unless supplied.",
        ],
        analysis={
            "unit_economics": economics,
            "decision_rule": "Do not scale acquisition until retained paid-customer contribution is positive under the approved cash guardrail.",
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
    inputs = normalized_inputs(context)
    business_name = str(inputs["business_name"])
    metrics, source, synthetic = _dataset(context)
    economics = calculate_unit_economics(metrics)
    values = economics["metrics"]
    contribution = values.get("monthly_contribution_after_fixed_costs_and_acquisition")
    packet = build_packet(
        context,
        stage="publish_financial_control_packet",
        objective=f"Publish an approval-ready financial control packet for {business_name}'s business-success goal.",
        trigger="The deterministic unit-economics calculation is complete.",
        sources=[source],
        observed_facts=[
            f"Modeled monthly contribution is {_money(contribution, economics['currency'])}.",
            f"The calculation has {len(economics['missing_inputs'])} missing required inputs.",
        ],
        assumptions=economics["formula_notes"],
        analysis={
            "unit_economics": economics,
            "financial_status": "review_required",
        },
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
        artifact_type="business_finance_control_brief",
        executive_summary=f"The Business Finance co-worker calculated {business_name}'s contribution economics from supplied inputs and converted uncertainty into explicit cash and approval guardrails.",
        evidence={"unit_economics": economics, "model_status": "synthetic_demo" if synthetic else economics["status"]},
        next_steps=[
            "Replace synthetic inputs with reconciled billing, cost, cash, refund, and cohort exports.",
            "Confirm which direct content and support costs are included in gross margin.",
            "Set a founder-approved experiment cash limit.",
            "Record finance thresholds and aggregate results as explicit human-reviewed cross-functional handoffs.",
        ],
        data_status="synthetic_demo" if synthetic else economics["status"],
        role_contribution="Translate growth, retention, pricing, production, and operating choices into cash, contribution, payback, and break-even guardrails.",
        north_star_question="Can the business acquire and retain customers while generating enough contribution to fund safe, reliable delivery?",
        role_scorecard=[
            {"metric": "monthly_contribution", "current": contribution, "unit": economics["currency"], "target": "positive and reconciled", "decision_use": "Determines whether the operating model funds itself."},
            {"metric": "blended_cac", "current": values.get("blended_cac"), "unit": economics["currency"], "target": "below retained-customer contribution guardrail", "decision_use": "Constrains Growth experiments."},
            {"metric": "cac_payback_months", "current": values.get("modeled_cac_payback_months"), "target": "founder-approved and supported by retained cohorts", "decision_use": "Prevents cash from being trapped in weak channels."},
            {"metric": "monthly_churn_rate", "current": values.get("monthly_churn_rate"), "target": "declining with cohort evidence", "decision_use": "Connects Lifecycle outcomes to affordability."},
            {"metric": "break_even_paying_customers", "current": values.get("break_even_paying_customers"), "target": "credible path within available cash and capacity", "decision_use": "Frames scale and runway requirements."},
        ],
        founder_decisions=[
            {"decision": "Approve the 90-day experiment cash ceiling", "why_now": "Growth and product learning must remain affordable before economics are fully observed."},
            {"decision": "Accept, revise, or stop the current pricing and channel assumptions", "why_now": "Synthetic or missing inputs cannot authorize spend, but they expose which assumptions drive viability."},
            {"decision": "Assign owners for missing reconciled inputs", "why_now": "Billing, direct cost, churn, refund, cash, and liability coverage determine whether the model is decision-grade."},
        ],
        cross_functional_handoffs=[
            {"to": "growth_partnerships_lead", "provides": "maximum CAC, payback, and experiment cash limits", "needs_from": "channel-level qualified-conversation, conversion, and spend evidence"},
            {"to": "customer_lifecycle_director", "provides": "churn and retained-value targets", "needs_from": "activation, retention, support-load, and cancellation evidence by cohort"},
            {"to": "content_studio_director", "provides": "content unit-cost and batch-budget limits", "needs_from": "production cost, revision rate, and reusable-component coverage"},
            {"to": "learning_quality_safety_director", "provides": "review-capacity and remediation cost visibility", "needs_from": "blocked/revise rates and mandatory review workload; safety gates are never waived for cost"},
        ],
        ninety_day_plan=[
            {"days": "0-30", "outcome": "Replace synthetic assumptions with a reconciled baseline and set a founder-approved experiment cash ceiling."},
            {"days": "31-60", "outcome": "Join channel, activation, churn, support, content-cost, and review-cost evidence into cohort contribution."},
            {"days": "61-90", "outcome": "Issue a scale/revise/stop recommendation with runway, break-even, downside, and evidence-quality scenarios."},
        ],
    )
    return {**persisted, **final}


def _money(value: Any, currency: str) -> str:
    return "not reported" if not isinstance(value, (int, float)) else f"{currency} {float(value):,.2f}"


def _number(value: Any) -> str:
    return "not reported" if not isinstance(value, (int, float)) else f"{float(value):,.0f}"
