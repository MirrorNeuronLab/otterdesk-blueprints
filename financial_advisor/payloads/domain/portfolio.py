"""Portfolio context, deterministic market scenarios, risk, and bounded review."""

from .common import *
from .knowledge import load_prompt
from .review_services import actor_review, review_artifact
from .source_ingestion import *

def load_portfolio_from_documents(ctx: dict[str, Any]) -> dict[str, Any]:
    docs = ctx["state"]["workflow"]["financial_document_reader"]["documents"]
    for doc in docs:
        data = doc.get("data")
        if isinstance(data, dict) and isinstance(data.get("portfolio"), dict):
            return copy.deepcopy(data)
    payload = ctx["payload"]
    return {
        "portfolio": copy.deepcopy(payload.get("portfolio") or {}),
        "benchmark_portfolio": copy.deepcopy(payload.get("benchmark_portfolio") or {}),
        "risk_policy": copy.deepcopy(payload.get("risk_policy") or {}),
        "decision_constraints": copy.deepcopy(payload.get("decision_constraints") or {}),
    }

def step_portfolio_context_loader(ctx: dict[str, Any]) -> dict[str, Any]:
    loaded = load_portfolio_from_documents(ctx)
    portfolio = loaded.get("portfolio") if isinstance(loaded.get("portfolio"), dict) else {}
    holdings = portfolio.get("holdings") if isinstance(portfolio.get("holdings"), list) else []
    portfolio_source_refs = [
        doc["source_ref"]
        for doc in ctx["state"]["workflow"]["financial_document_reader"].get("documents", [])
        if isinstance(doc.get("data"), dict) and isinstance(doc.get("data", {}).get("portfolio"), dict)
    ]
    if not portfolio_source_refs and ctx["payload"].get("portfolio"):
        portfolio_source_refs = ["workflow_input:portfolio"]
    policy = loaded.get("risk_policy") or {}
    policy_metadata = copy.deepcopy(
        loaded.get("risk_policy_metadata")
        or policy.get("metadata")
        or ctx["payload"].get("risk_policy_metadata")
        or {}
    )
    policy_customer_specific = bool(policy_metadata.get("customer_specific", False))
    policy_provenance = {
        "source": policy_metadata.get("source") or (portfolio_source_refs[0] if portfolio_source_refs else "workflow_input:risk_policy"),
        "source_ref": portfolio_source_refs[0] if portfolio_source_refs else "workflow_input:risk_policy",
        "version": policy_metadata.get("version") or "unversioned",
        "effective_date": policy_metadata.get("effective_date"),
        "customer_specific": policy_customer_specific,
        "status": "customer_policy" if policy_customer_specific else "screening_threshold",
        "applied_because": (
            "A customer-specific investment policy was supplied."
            if policy_customer_specific
            else "No signed customer investment policy with provenance was supplied; limits are screening thresholds only."
        ),
    }
    profile = copy.deepcopy(ctx["payload"].get("customer_profile") or ctx["payload"].get("investment_profile") or {})
    return {
        "portfolio": portfolio,
        "benchmark_portfolio": loaded.get("benchmark_portfolio") or {},
        "risk_policy": loaded.get("risk_policy") or {},
        "decision_constraints": loaded.get("decision_constraints") or {},
        "portfolio_source_refs": portfolio_source_refs,
        "risk_policy_provenance": policy_provenance,
        "customer_profile": profile,
        "customer_profile_status": customer_profile_status(profile),
        "holding_count": len(holdings),
        "symbols": sorted({str(item.get("symbol", "")).upper() for item in holdings if isinstance(item, dict) and item.get("symbol")}),
        "warnings": [] if holdings else ["no_portfolio_holdings_detected"],
    }

def deterministic_price(symbol: str) -> float:
    symbol = symbol.upper()
    if symbol in DEFAULT_MARKET_PRICES:
        return DEFAULT_MARKET_PRICES[symbol]
    return 25.0 + (sum(ord(char) for char in symbol) % 200)

def step_portfolio_market_data_loader(ctx: dict[str, Any]) -> dict[str, Any]:
    context = ctx["state"]["workflow"]["portfolio_context_loader"]
    series = {}
    for symbol in context.get("symbols") or []:
        price = deterministic_price(symbol)
        series[symbol] = {
            "symbol": symbol,
            "last_price": price,
            "source_ref": f"deterministic_market_fixture:{symbol}",
            "freshness": "fixture",
            "as_of": utc_now_iso(),
        }
    return {
        "provider": "deterministic_public_market_fixture",
        "series": series,
        "source_refs": [item["source_ref"] for item in series.values()],
        "warnings": ["market_data_is_fixture_for_local_review"],
    }

def step_portfolio_risk_engine(ctx: dict[str, Any]) -> dict[str, Any]:
    context = ctx["state"]["workflow"]["portfolio_context_loader"]
    market = ctx["state"]["workflow"]["portfolio_market_data_loader"]
    portfolio = context.get("portfolio") or {}
    holdings = portfolio.get("holdings") if isinstance(portfolio.get("holdings"), list) else []
    cash = float(portfolio.get("cash") or 0.0)
    marked_holdings = []
    invested_value = 0.0
    weighted_risk = 0.0
    for item in holdings:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        quantity = float(item.get("quantity") or 0.0)
        asset_class = str(item.get("asset_class") or "other").lower()
        instrument_type = instrument_type_for_holding(item, symbol)
        market_quote = (market.get("series") or {}).get(symbol, {})
        price = float(market_quote.get("last_price") or deterministic_price(symbol))
        value = quantity * price
        invested_value += value
        weighted_risk += value * RISK_BY_ASSET_CLASS.get(asset_class, RISK_BY_ASSET_CLASS["other"])
        marked_holdings.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "asset_class": asset_class,
                "instrument_type": instrument_type,
                "concentration_category": concentration_category(instrument_type, asset_class),
                "price": price,
                "price_source_ref": market_quote.get("source_ref") or f"deterministic_market_fixture:{symbol}",
                "price_freshness": market_quote.get("freshness") or "unknown",
                "price_as_of": market_quote.get("as_of"),
                "market_value": value,
            }
        )
    total_value = invested_value + cash
    for item in marked_holdings:
        item["weight_pct"] = round((item["market_value"] / total_value * 100) if total_value else 0.0, 2)
    cash_weight = (cash / total_value * 100) if total_value else 0.0
    largest = max((item["weight_pct"] for item in marked_holdings), default=0.0)
    annual_vol = (weighted_risk / invested_value * 100) if invested_value else 0.0
    var_pct = annual_vol / (252 ** 0.5) * 1.65 if annual_vol else 0.0
    cvar_pct = var_pct * 1.25
    policy = context.get("risk_policy") or {}
    provenance = context.get("risk_policy_provenance") or {}
    policy_customer_specific = bool(provenance.get("customer_specific"))
    threshold_breaches = []
    if largest > float(policy.get("max_single_name_weight_pct") or 100):
        threshold_breaches.append("position_weight_above_threshold")
    if cash_weight < float(policy.get("min_cash_pct") or 0):
        threshold_breaches.append("cash_below_threshold")
    if var_pct > float(policy.get("max_var_pct") or 100):
        threshold_breaches.append("var_above_threshold")
    if cvar_pct > float(policy.get("max_cvar_pct") or 100):
        threshold_breaches.append("cvar_above_threshold")
    violations = list(threshold_breaches) if policy_customer_specific else []
    screening_flags = [] if policy_customer_specific else list(threshold_breaches)
    largest_position = max(marked_holdings, key=lambda item: item.get("weight_pct", 0.0), default=None)
    risk_engine_config = ctx["config"].get("risk_engine") if isinstance(ctx["config"].get("risk_engine"), dict) else {}
    var_confidence = float(risk_engine_config.get("var_confidence") or 0.95)
    cvar_confidence = float(risk_engine_config.get("cvar_confidence") or var_confidence)
    risk_methodology = {
        "method": "deterministic asset-class risk proxy",
        "confidence_level": var_confidence,
        "cvar_confidence_level": cvar_confidence,
        "holding_period": "one trading day proxy",
        "lookback_period": "not applicable; no historical return series supplied",
        "return_frequency": "not applicable; proxy uses asset-class risk assumptions",
        "cash_included": True,
        "price_data": market.get("provider"),
        "interpretation": "VaR-style and CVaR-style values are model estimates for review, not forecasts or guarantees.",
        "estimated_adverse_day_loss": round(total_value * var_pct / 100, 2),
        "estimated_cvar_loss": round(total_value * cvar_pct / 100, 2),
    }
    policy_results = {
        "maximum_position_weight": {
            "policy": "Maximum weight in one security or fund",
            "limit_pct": policy.get("max_single_name_weight_pct"),
            "observed_pct": round(largest, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and largest > float(policy.get("max_single_name_weight_pct") or 100) else (
                "screening_threshold_breach" if largest > float(policy.get("max_single_name_weight_pct") or 100) else "within_threshold"
            ),
        },
        "minimum_cash": {
            "policy": "Minimum cash weight",
            "limit_pct": policy.get("min_cash_pct"),
            "observed_pct": round(cash_weight, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and cash_weight < float(policy.get("min_cash_pct") or 0) else (
                "screening_threshold_breach" if cash_weight < float(policy.get("min_cash_pct") or 0) else "within_threshold"
            ),
        },
        "maximum_var": {
            "policy": "Maximum one-day VaR-style estimate",
            "limit_pct": policy.get("max_var_pct"),
            "observed_pct": round(var_pct, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and var_pct > float(policy.get("max_var_pct") or 100) else (
                "screening_threshold_breach" if var_pct > float(policy.get("max_var_pct") or 100) else "within_threshold"
            ),
        },
        "maximum_cvar": {
            "policy": "Maximum one-day CVaR-style estimate",
            "limit_pct": policy.get("max_cvar_pct"),
            "observed_pct": round(cvar_pct, 2),
            "source": provenance.get("source"),
            "source_ref": provenance.get("source_ref"),
            "version": provenance.get("version"),
            "effective_date": provenance.get("effective_date"),
            "customer_specific": policy_customer_specific,
            "status": "violation" if policy_customer_specific and cvar_pct > float(policy.get("max_cvar_pct") or 100) else (
                "screening_threshold_breach" if cvar_pct > float(policy.get("max_cvar_pct") or 100) else "within_threshold"
            ),
        },
    }
    candidate_actions = ["no_action"]
    if "position_weight_above_threshold" in threshold_breaches:
        candidate_actions.append("reduce_concentration")
    if "cash_below_threshold" in threshold_breaches:
        candidate_actions.append("raise_cash")
    if var_pct > 0:
        candidate_actions.append("review_risk_budget")
    finding = actor_review(
        ctx["config"],
        ctx["llm"],
        "portfolio_risk_engine",
        "Portfolio risk reviewed with deterministic fixture market data.",
        {
            "deterministic_risk_metrics": {
                "total_value": total_value,
                "cash_weight_pct": cash_weight,
                "largest_position_weight_pct": largest,
                "annualized_volatility_pct": annual_vol,
                "var_pct": var_pct,
                "cvar_pct": cvar_pct,
                "policy_violations": violations,
                "screening_threshold_flags": screening_flags,
                "risk_methodology": risk_methodology,
                "policy_results": policy_results,
            },
            "holdings": marked_holdings,
            "risk_policy": policy,
            "risk_policy_provenance": provenance,
            "market_source_refs": market.get("source_refs", []),
            "review_constraints": [
                "Do not change deterministic portfolio metrics.",
                "Do not recommend trades or money movement.",
                "Keep candidate actions review-only and human-approved.",
            ],
        },
        prompt_details=load_prompt("portfolio-llm-review.md"),
        active_knowledge=ctx.get("active_knowledge"),
    )
    profile_status = context.get("customer_profile_status") or {}
    suitability_complete = profile_status.get("status") == "complete"
    return {
        "base_currency": portfolio.get("base_currency", "USD"),
        "total_value": total_value,
        "cash": cash,
        "cash_weight_pct": round(cash_weight, 2),
        "holdings": marked_holdings,
        "largest_position_weight_pct": round(largest, 2),
        "largest_position": largest_position,
        "annualized_volatility_pct": round(annual_vol, 2),
        "var_pct": round(var_pct, 2),
        "cvar_pct": round(cvar_pct, 2),
        "risk_methodology": risk_methodology,
        "risk_policy": copy.deepcopy(policy),
        "risk_policy_provenance": provenance,
        "policy_results": policy_results,
        "policy_violations": violations,
        "screening_threshold_flags": screening_flags,
        "suitability_assessment": {
            "status": profile_status.get("status", "not_assessable"),
            "missing_fields": profile_status.get("missing_fields", []),
            "reason": (
                "Customer objectives and constraints were supplied; suitability still requires current holdings, tax-lot basis, other-account coverage, and qualified human review."
                if suitability_complete
                else "Allocation appropriateness cannot be assessed without the customer's purpose, time horizon, liquidity needs, risk tolerance, and tax context."
            ),
        },
        "candidate_actions": candidate_actions,
        "review_only": True,
        "actor_finding": finding,
        "warnings": ["risk_metrics_are_review_estimates_not_trade_instructions"],
    }

def step_portfolio_llm_reviewer(ctx: dict[str, Any]) -> dict[str, Any]:
    workflow = ctx["state"]["workflow"]
    context = workflow["portfolio_context_loader"]
    market = workflow["portfolio_market_data_loader"]
    risk = workflow["portfolio_risk_engine"]
    source_refs = sorted(
        {str(item) for item in market.get("source_refs", []) if item}
        | {
            str(item.get("symbol"))
            for item in risk.get("holdings", [])
            if item.get("symbol")
        }
        | {str(item) for item in context.get("portfolio_source_refs", []) if item}
        | {
            str(context.get("risk_policy_provenance", {}).get("source_ref"))
            for _ in [0]
            if context.get("risk_policy_provenance", {}).get("source_ref")
        }
    )
    evidence_gaps = []
    if not context.get("holding_count"):
        evidence_gaps.append("No portfolio holdings were available for risk review.")
    if market.get("provider") == "deterministic_public_market_fixture":
        evidence_gaps.append("Market prices are deterministic fixtures and need live/source verification for production use.")
    if not context.get("risk_policy"):
        evidence_gaps.append("No explicit risk policy was provided for threshold review.")
    if (context.get("customer_profile_status") or {}).get("missing_fields"):
        evidence_gaps.append("Customer investment objectives and constraints are incomplete; suitability is not assessable.")
    if not (context.get("risk_policy_provenance") or {}).get("customer_specific") and risk.get("screening_threshold_flags"):
        evidence_gaps.append("Thresholds are unverified screening limits, not customer-specific policy violations.")
    risk_flags = list(risk.get("policy_violations") or []) + list(risk.get("screening_threshold_flags") or []) + list(risk.get("warnings") or [])
    return review_artifact(
        ctx,
        step_id="portfolio_llm_reviewer",
        summary="Portfolio LLM reviewer interpreted deterministic risk metrics, policy thresholds, source gaps, and human review questions.",
        context={
            "portfolio_context_loader": context,
            "portfolio_market_data_loader": market,
            "portfolio_risk_engine": risk,
            "review_constraints": [
                "Do not change portfolio values, weights, volatility, VaR, CVaR, or policy-violation math.",
                "Do not recommend executing trades, reallocations, or money movement.",
                "Only identify review questions, evidence gaps, and risk interpretation notes.",
            ],
        },
        source_refs=source_refs,
        key_findings=[
            f"Portfolio total value is {money(risk.get('total_value'))}.",
            f"Largest position weight is {risk.get('largest_position_weight_pct')}% with cash weight {risk.get('cash_weight_pct')}%.",
            (
                f"{risk.get('largest_position', {}).get('symbol')} is classified as a {risk.get('largest_position', {}).get('instrument_type')} and represents substantial fund/strategy concentration, not a single-company holding."
                if risk.get("largest_position") and risk.get("largest_position", {}).get("instrument_type") in {"etf", "mutual_fund", "fund", "index_fund"}
                else "Instrument type for the largest position is not verified from supplied holdings."
            ),
        ],
        review_questions=[
            "Does the risk policy reflect the user's current investment objective and constraints?",
            "Do fixture market prices need replacement with verified live market evidence before decision use?",
            "Are any screening-threshold breaches intentional exceptions under a documented customer policy?",
        ],
        evidence_gaps=evidence_gaps,
        risk_flags=risk_flags,
        next_steps=[
            "Verify portfolio holdings, cash, and market prices against source account evidence.",
            "Have a human reviewer verify policy provenance and evaluate any threshold flags before an allocation decision.",
        ],
    )

__all__ = ["step_portfolio_context_loader", "step_portfolio_llm_reviewer", "step_portfolio_market_data_loader", "step_portfolio_risk_engine"]
