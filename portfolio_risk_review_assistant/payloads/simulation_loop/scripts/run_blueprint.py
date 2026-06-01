#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import math
import random
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

try:
    from mn_blueprint_support import (
        architecture_contract,
        create_runtime_context,
        get_llm_client,
        load_config,
        resolve_input_overrides,
        run_blueprint_cli,
        utc_now_iso,
    )
    from mn_blueprint_support.web_ui import maybe_write_static_output
except ModuleNotFoundError:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "mn-skills" / "blueprint_support_skill" / "src"
        if candidate.exists():
            sys.path.insert(0, str(candidate))
            break
    from mn_blueprint_support import (
        architecture_contract,
        create_runtime_context,
        get_llm_client,
        load_config,
        resolve_input_overrides,
        run_blueprint_cli,
        utc_now_iso,
    )
    from mn_blueprint_support.web_ui import maybe_write_static_output


BLUEPRINT_ID = "portfolio_risk_review_assistant"
BLUEPRINT_NAME = "Portfolio Risk Review Assistant"
CATEGORY = "finance"
DESCRIPTION = (
    "Review-only real-time portfolio risk advisor using public market data, "
    "financial engineering simulation, and LLM-written reports."
)
TRADING_DAYS = 252


class MarketDataClient(Protocol):
    provider: str

    def history(self, symbol: str, *, range_: str, interval: str, timeout_seconds: float) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class PublicYahooChartClient:
    provider: str = "public_yahoo_chart"
    base_url: str = "https://query1.finance.yahoo.com/v8/finance/chart"

    def history(self, symbol: str, *, range_: str, interval: str, timeout_seconds: float) -> dict[str, Any]:
        params = urllib.parse.urlencode({"range": range_, "interval": interval, "includePrePost": "false"})
        url = f"{self.base_url}/{urllib.parse.quote(symbol.upper())}?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "MirrorNeuronBlueprint/1.0"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not result:
            error = (payload.get("chart") or {}).get("error")
            raise RuntimeError(f"no chart result for {symbol}: {error}")
        return result


def run_blueprint(
    blueprint_id: str = BLUEPRINT_ID,
    *,
    inputs: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    market_data_client: MarketDataClient | None = None,
    config: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    config_json: str | None = None,
    run_id: str | None = None,
    runs_root: str | Path | None = None,
    input_adapter: str | None = None,
    input_file: str | Path | None = None,
    write_run_store: bool | None = None,
) -> dict[str, Any]:
    if blueprint_id != BLUEPRINT_ID:
        raise ValueError(f"this runner handles {BLUEPRINT_ID!r}, got {blueprint_id!r}")

    started_at = utc_now_iso()
    default_config_path = next(
        (
            parent / "config" / "default.json"
            for parent in Path(__file__).resolve().parents
            if (parent / "config" / "default.json").exists()
        ),
        Path(__file__).resolve().parents[3] / "config" / "default.json",
    )
    resolved_config = load_config(
        BLUEPRINT_ID,
        default_config_path=default_config_path,
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
    runtime_inputs = default_inputs()
    runtime_inputs.update(adapter_inputs)
    runtime_inputs.update(inputs or {})
    runtime_inputs = normalize_runtime_inputs(runtime_inputs, resolved_config)

    llm_mode = str((resolved_config.get("llm") or {}).get("mode") or "ollama")
    llm = llm_client or get_llm_client("fake" if llm_mode in {"fake", "mock"} else None)
    data_client = market_data_client or PublicYahooChartClient()
    context = create_runtime_context(BLUEPRINT_ID, resolved_config, runtime_inputs, input_source)
    context.start()
    try:
        context.status("loading_inputs", "running", component="portfolio_risk_engine", progress=0.1)
        portfolio = normalize_portfolio(runtime_inputs["portfolio"])
        policy = runtime_inputs["risk_policy"]
        constraints = runtime_inputs["decision_constraints"]
        symbols = sorted({holding["symbol"] for holding in portfolio["holdings"]} | set(runtime_inputs["benchmark_portfolio"]))

        market_data = load_market_data(symbols, resolved_config["market_data"], data_client)
        context.event(
            "market_data_loaded",
            {
                "provider": getattr(data_client, "provider", "unknown"),
                "symbols": symbols,
                "source_refs": [series["source_ref"] for series in market_data.values()],
                "freshness": {symbol: series["freshness"] for symbol, series in market_data.items()},
            },
        )

        context.status("running_worker", "running", component="portfolio_risk_engine", progress=0.35)
        risk_state = compute_risk_state(portfolio, market_data, policy, resolved_config["risk_engine"])
        context.event("risk_state_computed", summarize_risk_state(risk_state))

        candidates = propose_decision_candidates(portfolio, risk_state, constraints, resolved_config["decision_policy"])
        context.event(
            "decision_candidates_proposed",
            {"candidate_ids": [candidate["id"] for candidate in candidates], "count": len(candidates)},
        )

        marked_portfolio = {
            "base_currency": portfolio["base_currency"],
            "cash": portfolio["cash"],
            "holdings": copy.deepcopy(risk_state["holdings"]),
        }
        simulations: list[dict[str, Any]] = []
        for candidate in candidates:
            adjusted = apply_candidate(marked_portfolio, candidate)
            sim = simulate_candidate(
                adjusted,
                market_data,
                policy,
                resolved_config["monte_carlo"],
                resolved_config["risk_engine"],
            )
            sim["candidate"] = candidate
            simulations.append(sim)
            context.event(
                "decision_simulated",
                {
                    "candidate_id": candidate["id"],
                    "expected_return_pct": sim["summary"]["expected_return_pct"],
                    "var_pct": sim["summary"]["var_pct"],
                    "cvar_pct": sim["summary"]["cvar_pct"],
                    "policy_violations": sim["policy_violations"],
                },
            )

        benchmark = evaluate_and_benchmark(simulations, risk_state, policy, resolved_config["benchmark"])
        context.event("decision_evaluated", {"ranked_candidate_ids": [row["candidate_id"] for row in benchmark["ranking"]]})
        context.event("benchmark_step_scored", benchmark)

        best = benchmark["ranking"][0]
        report_packet = llm_report(
            llm,
            runtime_inputs,
            risk_state,
            benchmark,
            market_data,
            fallback_action=best["action"],
        )
        context.event(
            "llm_report_written",
            {
                "provider": getattr(llm, "provider", "unknown"),
                "model": getattr(llm, "model", "unknown"),
                "action": report_packet["recommended_action"],
                "confidence": report_packet["confidence"],
            },
        )

        final = final_artifact(runtime_inputs, risk_state, simulations, benchmark, report_packet, market_data)
        result = {
            "identity": {
                "blueprint_id": context.blueprint_id,
                "name": context.name,
                "run_id": context.run_id,
            },
            "blueprint": BLUEPRINT_ID,
            "name": BLUEPRINT_NAME,
            "category": CATEGORY,
            "description": DESCRIPTION,
            "run": {
                "run_id": context.run_id,
                "run_dir": str(context.run_dir) if context.run_dir else None,
                "started_at": started_at,
                "ended_at": utc_now_iso(),
                "status": "completed",
            },
            "architecture": architecture_contract(resolved_config, input_source),
            "config": resolved_config,
            "inputs": runtime_inputs,
            "input_source": input_source,
            "agent_roles": ["market_data_loader", "risk_engine", "monte_carlo_simulator", "llm_report_writer"],
            "runtime_features": [
                "public market data",
                "risk feature engineering",
                "monte carlo simulation",
                "decision benchmarking",
                "LLM market-signal report writing",
            ],
            "uses_simulation": True,
            "uses_llm": True,
            "risk_state": risk_state,
            "simulations": simulations,
            "benchmark": benchmark,
            "market_data": market_data_summary(market_data),
            "final_artifact": final,
            "artifacts": artifact_records(),
            "llm": {
                "provider": getattr(llm, "provider", "unknown"),
                "model": getattr(llm, "model", "unknown"),
                "calls": getattr(llm, "calls", 0),
                "fallback_calls": getattr(llm, "fallback_calls", 0),
            },
        }
        web_ui = maybe_write_static_output(context.run_store, result, resolved_config)
        if web_ui:
            result["web_ui"] = web_ui.to_dict()
        context.status("completed", "completed", component="portfolio_risk_engine", progress=1.0)
        context.finish(result)
        return result
    except Exception as error:
        context.fail(error)
        raise


def default_inputs() -> dict[str, Any]:
    return {
        "seed": 42,
        "portfolio": {
            "base_currency": "USD",
            "cash": 50000.0,
            "holdings": [
                {"symbol": "SPY", "quantity": 180, "asset_class": "equity", "liquidity": "daily"},
                {"symbol": "AGG", "quantity": 300, "asset_class": "rates", "liquidity": "daily"},
                {"symbol": "GLD", "quantity": 80, "asset_class": "commodity", "liquidity": "daily"},
            ],
        },
        "risk_policy": {
            "max_drawdown_pct": 15.0,
            "max_var_pct": 8.0,
            "max_cvar_pct": 11.0,
            "max_single_name_weight_pct": 45.0,
            "min_cash_pct": 5.0,
            "max_turnover_pct": 15.0,
        },
        "decision_constraints": {
            "allowed_actions": [
                "no_action",
                "raise_cash",
                "reduce_concentration",
                "reduce_equity_beta",
                "duration_hedge",
                "credit_risk_reduction",
            ],
            "restricted_symbols": [],
            "review_only": True,
        },
        "market_signals": [],
        "benchmark_portfolio": {"SPY": 0.6, "AGG": 0.3, "GLD": 0.1},
    }


def normalize_runtime_inputs(inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(inputs)
    payload = ((config.get("inputs") or {}).get("payload") or {})
    for key in ("portfolio", "risk_policy", "decision_constraints", "market_signals", "benchmark_portfolio", "seed"):
        if key not in normalized and key in payload:
            normalized[key] = copy.deepcopy(payload[key])
    normalized["seed"] = int(normalized.get("seed", (config.get("monte_carlo") or {}).get("seed", 42)))
    if "simulation_horizon_days" in normalized:
        config.setdefault("monte_carlo", {})["horizon_days"] = int(normalized["simulation_horizon_days"])
    if "monte_carlo_paths" in normalized:
        config.setdefault("monte_carlo", {})["paths"] = int(normalized["monte_carlo_paths"])
    normalized["benchmark_portfolio"] = normalize_benchmark_symbols(normalized.get("benchmark_portfolio") or {})
    return normalized


def normalize_portfolio(portfolio: dict[str, Any]) -> dict[str, Any]:
    holdings = []
    for raw in portfolio.get("holdings") or []:
        symbol = str(raw.get("symbol") or "").upper().strip()
        if not symbol:
            raise ValueError("portfolio holdings must include symbol")
        quantity = float(raw.get("quantity") or 0.0)
        market_value = raw.get("market_value")
        if quantity <= 0 and market_value is None:
            raise ValueError(f"holding {symbol} must include quantity or market_value")
        holdings.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "market_value": float(market_value) if market_value is not None else None,
                "asset_class": str(raw.get("asset_class") or "unknown"),
                "liquidity": str(raw.get("liquidity") or "daily"),
                "cost_basis": float(raw["cost_basis"]) if raw.get("cost_basis") is not None else None,
            }
        )
    if not holdings:
        raise ValueError("portfolio.holdings is required")
    return {
        "base_currency": str(portfolio.get("base_currency") or "USD"),
        "cash": float(portfolio.get("cash") or 0.0),
        "holdings": holdings,
    }


def normalize_benchmark_symbols(benchmark: dict[str, Any]) -> dict[str, float]:
    weights = {str(symbol).upper(): float(weight) for symbol, weight in benchmark.items()}
    total = sum(max(0.0, weight) for weight in weights.values())
    if total <= 0:
        return {"SPY": 0.6, "AGG": 0.3, "GLD": 0.1}
    return {symbol: max(0.0, weight) / total for symbol, weight in weights.items()}


def load_market_data(
    symbols: list[str],
    config: dict[str, Any],
    client: MarketDataClient,
) -> dict[str, dict[str, Any]]:
    history_range = str(config.get("history_range") or "1y")
    interval = str(config.get("interval") or "1d")
    timeout = float(config.get("timeout_seconds") or 8.0)
    stale_seconds = float(config.get("stale_after_seconds") or 259200)
    retry = config.get("retry") or {}
    max_attempts = max(1, int(retry.get("max_attempts") or 1))
    backoff_seconds = max(0.0, float(retry.get("backoff_seconds") or 0.0))
    loaded = {}
    errors = {}
    now = time.time()
    for symbol in symbols:
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                raw = client.history(symbol, range_=history_range, interval=interval, timeout_seconds=timeout)
                series = parse_yahoo_chart(symbol, raw, now=now, stale_after_seconds=stale_seconds)
                loaded[symbol] = series
                break
            except Exception as exc:
                last_error = exc
                if attempt + 1 < max_attempts and backoff_seconds:
                    time.sleep(backoff_seconds * (2**attempt))
        else:
            errors[symbol] = str(last_error)
    if errors:
        raise RuntimeError(f"required market data failed closed: {errors}")
    return loaded


def parse_yahoo_chart(symbol: str, raw: dict[str, Any], *, now: float, stale_after_seconds: float) -> dict[str, Any]:
    timestamps = raw.get("timestamp") or []
    quote = (((raw.get("indicators") or {}).get("quote") or [{}])[0])
    closes = quote.get("close") or []
    prices = [
        {"timestamp": int(ts), "close": float(close)}
        for ts, close in zip(timestamps, closes)
        if close is not None and float(close) > 0
    ]
    if len(prices) < 30:
        raise ValueError(f"{symbol} returned fewer than 30 usable closes")
    last_ts = prices[-1]["timestamp"]
    age_seconds = max(0.0, now - float(last_ts))
    if age_seconds > stale_after_seconds:
        raise ValueError(f"{symbol} market data is stale by {round(age_seconds)} seconds")
    return {
        "symbol": symbol.upper(),
        "provider": "public_yahoo_chart",
        "prices": prices,
        "last_price": prices[-1]["close"],
        "last_timestamp": datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat(),
        "returns": percent_returns([item["close"] for item in prices]),
        "source_ref": f"market:{symbol.upper()}:{last_ts}",
        "freshness": {"age_seconds": round(age_seconds, 3), "stale_after_seconds": stale_after_seconds},
    }


def percent_returns(prices: list[float]) -> list[float]:
    return [(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices)) if prices[i - 1] > 0]


def compute_risk_state(
    portfolio: dict[str, Any],
    market_data: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    risk_config: dict[str, Any],
) -> dict[str, Any]:
    holdings = mark_holdings(portfolio, market_data)
    total_value = portfolio_total_value(holdings, portfolio["cash"])
    weights = {holding["symbol"]: holding["market_value"] / total_value for holding in holdings}
    returns_by_symbol = {symbol: data["returns"] for symbol, data in market_data.items() if symbol in weights}
    portfolio_returns = weighted_returns(weights, returns_by_symbol)
    var_level = float(risk_config.get("var_confidence", 0.95))
    cvar_level = float(risk_config.get("cvar_confidence", 0.95))
    concentration = max(weights.values()) * 100.0 if weights else 0.0
    cash_pct = portfolio["cash"] / total_value * 100.0 if total_value else 0.0
    benchmark_symbol = str(risk_config.get("beta_proxy_symbol") or "SPY").upper()
    beta = beta_to_proxy(portfolio_returns, (market_data.get(benchmark_symbol) or {}).get("returns") or [])
    metrics = {
        "portfolio_value": round(total_value, 2),
        "cash_pct": round(cash_pct, 4),
        "volatility_pct": round(annualized_volatility(portfolio_returns) * 100.0, 4),
        "var_pct": round(abs(value_at_risk(portfolio_returns, var_level)) * 100.0, 4),
        "cvar_pct": round(abs(conditional_value_at_risk(portfolio_returns, cvar_level)) * 100.0, 4),
        "max_drawdown_pct": round(abs(max_drawdown(portfolio_returns)) * 100.0, 4),
        "single_name_concentration_pct": round(concentration, 4),
        "equity_beta": round(beta, 4),
    }
    return {
        "holdings": holdings,
        "weights": {symbol: round(weight, 6) for symbol, weight in weights.items()},
        "returns": portfolio_returns,
        "metrics": metrics,
        "policy_violations": policy_violations(metrics, policy),
        "source_refs": [market_data[symbol]["source_ref"] for symbol in weights],
    }


def mark_holdings(portfolio: dict[str, Any], market_data: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    marked = []
    for holding in portfolio["holdings"]:
        price = float(market_data[holding["symbol"]]["last_price"])
        value = holding["market_value"] if holding["market_value"] is not None else holding["quantity"] * price
        marked.append({**holding, "last_price": round(price, 4), "market_value": round(float(value), 2)})
    return marked


def portfolio_total_value(holdings: list[dict[str, Any]], cash: float) -> float:
    return sum(float(holding["market_value"]) for holding in holdings) + float(cash)


def weighted_returns(weights: dict[str, float], returns_by_symbol: dict[str, list[float]]) -> list[float]:
    length = min((len(values) for values in returns_by_symbol.values()), default=0)
    if length <= 0:
        return []
    aligned = {symbol: values[-length:] for symbol, values in returns_by_symbol.items()}
    return [sum(weights.get(symbol, 0.0) * aligned[symbol][i] for symbol in aligned) for i in range(length)]


def covariance(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size < 2:
        return 0.0
    lx, rx = left[-size:], right[-size:]
    lm, rm = statistics.fmean(lx), statistics.fmean(rx)
    return sum((x - lm) * (y - rm) for x, y in zip(lx, rx)) / (size - 1)


def beta_to_proxy(returns: list[float], proxy_returns: list[float]) -> float:
    var = covariance(proxy_returns, proxy_returns)
    return covariance(returns, proxy_returns) / var if var else 0.0


def annualized_volatility(returns: list[float]) -> float:
    return statistics.stdev(returns) * math.sqrt(TRADING_DAYS) if len(returns) > 1 else 0.0


def value_at_risk(returns: list[float], confidence: float) -> float:
    if not returns:
        return 0.0
    ordered = sorted(returns)
    index = max(0, min(len(ordered) - 1, int(math.floor((1.0 - confidence) * len(ordered)))))
    return ordered[index]


def conditional_value_at_risk(returns: list[float], confidence: float) -> float:
    threshold = value_at_risk(returns, confidence)
    tail = [value for value in returns if value <= threshold]
    return statistics.fmean(tail) if tail else threshold


def max_drawdown(returns: list[float]) -> float:
    wealth = 1.0
    peak = 1.0
    worst = 0.0
    for ret in returns:
        wealth *= 1.0 + ret
        peak = max(peak, wealth)
        worst = min(worst, (wealth / peak) - 1.0)
    return worst


def policy_violations(metrics: dict[str, float], policy: dict[str, Any]) -> list[str]:
    checks = [
        ("max_drawdown_pct", "max_drawdown_pct", ">"),
        ("var_pct", "max_var_pct", ">"),
        ("cvar_pct", "max_cvar_pct", ">"),
        ("single_name_concentration_pct", "max_single_name_weight_pct", ">"),
        ("cash_pct", "min_cash_pct", "<"),
    ]
    violations = []
    for metric_key, policy_key, op in checks:
        if policy_key not in policy:
            continue
        metric, limit = float(metrics.get(metric_key, 0.0)), float(policy[policy_key])
        if (op == ">" and metric > limit) or (op == "<" and metric < limit):
            violations.append(f"{metric_key} {metric:.2f} breaches {policy_key} {limit:.2f}")
    return violations


def propose_decision_candidates(
    portfolio: dict[str, Any],
    risk_state: dict[str, Any],
    constraints: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    allowed = set(constraints.get("allowed_actions") or [])
    restricted = {str(symbol).upper() for symbol in constraints.get("restricted_symbols") or []}
    candidates = [{"id": "no_action", "action": "no_action", "turnover_pct": 0.0, "description": "Keep current allocation under review."}]
    templates = [
        ("raise_cash", "Raise cash by trimming liquid risk assets.", 0.08),
        ("reduce_concentration", "Trim the largest unrestricted concentration.", 0.10),
        ("reduce_equity_beta", "Reduce equity beta using proportional equity sleeve trimming.", 0.12),
        ("duration_hedge", "Shift part of equity risk toward duration-sensitive defensive exposure.", 0.08),
        ("credit_risk_reduction", "Reduce credit-like or high-volatility exposures.", 0.08),
    ]
    max_turnover = float(policy.get("max_turnover_pct") or 15.0)
    for action, description, turnover in templates:
        if allowed and action not in allowed:
            continue
        if turnover * 100.0 > max_turnover:
            continue
        target_symbols = candidate_targets(action, risk_state, restricted)
        if action != "raise_cash" and not target_symbols:
            continue
        candidates.append(
            {
                "id": action,
                "action": action,
                "description": description,
                "turnover_pct": round(turnover * 100.0, 3),
                "target_symbols": target_symbols,
                "review_only": True,
            }
        )
    return candidates


def candidate_targets(action: str, risk_state: dict[str, Any], restricted: set[str]) -> list[str]:
    holdings = [holding for holding in risk_state["holdings"] if holding["symbol"] not in restricted]
    if not holdings:
        return []
    if action == "reduce_concentration":
        return [max(holdings, key=lambda item: item["market_value"])["symbol"]]
    if action == "reduce_equity_beta":
        return [holding["symbol"] for holding in holdings if holding.get("asset_class") == "equity"]
    if action == "duration_hedge":
        return [holding["symbol"] for holding in holdings if holding.get("asset_class") in {"equity", "commodity"}]
    if action == "credit_risk_reduction":
        return [holding["symbol"] for holding in holdings if holding.get("asset_class") in {"credit", "high_yield", "unknown"}]
    return [holding["symbol"] for holding in holdings]


def apply_candidate(portfolio: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    adjusted = copy.deepcopy(portfolio)
    action = candidate["action"]
    turnover = float(candidate.get("turnover_pct") or 0.0) / 100.0
    if action == "no_action" or turnover <= 0:
        return adjusted
    targets = set(candidate.get("target_symbols") or [holding["symbol"] for holding in adjusted["holdings"]])
    for holding in adjusted["holdings"]:
        if holding["symbol"] in targets:
            trim = (holding.get("market_value") or 0.0) * turnover
            holding["market_value"] = max(0.0, (holding.get("market_value") or 0.0) - trim)
            adjusted["cash"] += trim
    return adjusted


def simulate_candidate(
    portfolio: dict[str, Any],
    market_data: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    monte_config: dict[str, Any],
    risk_config: dict[str, Any],
) -> dict[str, Any]:
    paths = int(monte_config.get("paths") or 1000)
    horizon = int(monte_config.get("horizon_days") or 20)
    seed = int(monte_config.get("seed") or 42)
    marked = mark_holdings(portfolio, market_data)
    total = portfolio_total_value(marked, portfolio["cash"])
    weights = {holding["symbol"]: holding["market_value"] / total for holding in marked if total > 0}
    returns = weighted_returns(weights, {symbol: data["returns"] for symbol, data in market_data.items() if symbol in weights})
    mean_daily = statistics.fmean(returns) if returns else 0.0
    vol_daily = statistics.stdev(returns) if len(returns) > 1 else 0.0
    rng = random.Random(seed + sum(ord(ch) for ch in json.dumps(weights, sort_keys=True)))
    path_returns = []
    worst_drawdowns = []
    for _ in range(paths):
        wealth = 1.0
        peak = 1.0
        worst = 0.0
        for _day in range(horizon):
            shock = rng.gauss(mean_daily, vol_daily)
            wealth *= 1.0 + shock
            peak = max(peak, wealth)
            worst = min(worst, (wealth / peak) - 1.0)
        path_returns.append(wealth - 1.0)
        worst_drawdowns.append(worst)
    summary = {
        "paths": paths,
        "horizon_days": horizon,
        "expected_return_pct": round(statistics.fmean(path_returns) * 100.0, 4) if path_returns else 0.0,
        "var_pct": round(abs(value_at_risk(path_returns, float(risk_config.get("var_confidence", 0.95)))) * 100.0, 4),
        "cvar_pct": round(abs(conditional_value_at_risk(path_returns, float(risk_config.get("cvar_confidence", 0.95)))) * 100.0, 4),
        "worst_drawdown_pct": round(abs(min(worst_drawdowns or [0.0])) * 100.0, 4),
    }
    metrics = {
        "portfolio_value": round(total, 2),
        "cash_pct": round(portfolio["cash"] / total * 100.0, 4) if total else 0.0,
        "var_pct": summary["var_pct"],
        "cvar_pct": summary["cvar_pct"],
        "max_drawdown_pct": summary["worst_drawdown_pct"],
        "single_name_concentration_pct": round(max(weights.values()) * 100.0, 4) if weights else 0.0,
    }
    return {"summary": summary, "metrics": metrics, "policy_violations": policy_violations(metrics, policy)}


def evaluate_and_benchmark(
    simulations: list[dict[str, Any]],
    risk_state: dict[str, Any],
    policy: dict[str, Any],
    benchmark_config: dict[str, Any],
) -> dict[str, Any]:
    baseline = next(item for item in simulations if item["candidate"]["id"] == "no_action")
    rows = []
    for sim in simulations:
        score = candidate_score(sim, baseline, risk_state, policy)
        rows.append(
            {
                "candidate_id": sim["candidate"]["id"],
                "action": sim["candidate"]["action"],
                "quality_score": score,
                "expected_return_pct": sim["summary"]["expected_return_pct"],
                "var_pct": sim["summary"]["var_pct"],
                "cvar_pct": sim["summary"]["cvar_pct"],
                "worst_drawdown_pct": sim["summary"]["worst_drawdown_pct"],
                "policy_violations": sim["policy_violations"],
                "delta_vs_no_action": {
                    "var_pct": round(baseline["summary"]["var_pct"] - sim["summary"]["var_pct"], 4),
                    "cvar_pct": round(baseline["summary"]["cvar_pct"] - sim["summary"]["cvar_pct"], 4),
                    "worst_drawdown_pct": round(
                        baseline["summary"]["worst_drawdown_pct"] - sim["summary"]["worst_drawdown_pct"],
                        4,
                    ),
                },
            }
        )
    ranking = sorted(rows, key=lambda row: (-row["quality_score"], len(row["policy_violations"]), row["candidate_id"]))
    return {
        "schema_version": str(benchmark_config.get("schema_version") or "mn.finance.portfolio_risk.benchmark.v1"),
        "baseline": "no_action",
        "quality_metrics": benchmark_config.get("quality_metrics") or [],
        "ranking": ranking,
        "selected": ranking[0],
        "current_policy_violations": risk_state["policy_violations"],
    }


def candidate_score(sim: dict[str, Any], baseline: dict[str, Any], risk_state: dict[str, Any], policy: dict[str, Any]) -> float:
    del policy
    risk_improvement = (
        baseline["summary"]["var_pct"]
        - sim["summary"]["var_pct"]
        + baseline["summary"]["cvar_pct"]
        - sim["summary"]["cvar_pct"]
        + baseline["summary"]["worst_drawdown_pct"]
        - sim["summary"]["worst_drawdown_pct"]
    )
    return round(
        50.0
        + risk_improvement * 2.5
        + sim["summary"]["expected_return_pct"]
        - len(sim["policy_violations"]) * 8.0
        - max(0, len(risk_state["policy_violations"]) - len(sim["policy_violations"])) * -1.0,
        4,
    )


def llm_report(
    llm: Any,
    inputs: dict[str, Any],
    risk_state: dict[str, Any],
    benchmark: dict[str, Any],
    market_data: dict[str, dict[str, Any]],
    *,
    fallback_action: str,
) -> dict[str, Any]:
    fallback = {
        "recommended_action": fallback_action,
        "confidence": 0.78,
        "executive_summary": (
            f"Selected {fallback_action} after Monte Carlo and policy benchmarking. "
            "Review market freshness, constraints, and policy exceptions before acting."
        ),
        "market_signal_summary": summarize_market_signals(inputs.get("market_signals") or []),
        "rationale": "Structured simulation ranked this decision highest on risk reduction and policy fit.",
        "next_steps": [
            "Review policy violations and source timestamps.",
            "Confirm tax, mandate, and no-trade constraints.",
            "Approve, revise, or reject the review-only recommendation.",
        ],
    }
    prompt = {
        "market_signals": inputs.get("market_signals") or [],
        "risk_metrics": risk_state["metrics"],
        "policy_violations": risk_state["policy_violations"],
        "benchmark_selected": benchmark["selected"],
        "market_freshness": {symbol: data["freshness"] for symbol, data in market_data.items()},
    }
    response = llm.generate_json(
        system_prompt=(
            "You write concise portfolio risk review reports from structured financial metrics. "
            "Do not invent trades, prices, or source data. Return JSON only."
        ),
        user_prompt=json.dumps(prompt, sort_keys=True),
        fallback=fallback,
    )
    return {
        "recommended_action": str(response.get("recommended_action") or fallback["recommended_action"]),
        "confidence": float(response.get("confidence") or fallback["confidence"]),
        "executive_summary": str(response.get("executive_summary") or response.get("rationale") or fallback["executive_summary"]),
        "market_signal_summary": str(response.get("market_signal_summary") or fallback["market_signal_summary"]),
        "rationale": str(response.get("rationale") or fallback["rationale"]),
        "next_steps": response.get("next_steps") if isinstance(response.get("next_steps"), list) else fallback["next_steps"],
    }


def final_artifact(
    inputs: dict[str, Any],
    risk_state: dict[str, Any],
    simulations: list[dict[str, Any]],
    benchmark: dict[str, Any],
    report: dict[str, Any],
    market_data: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = benchmark["selected"]
    return {
        "type": "real-time portfolio risk review",
        "executive_summary": report["executive_summary"],
        "recommended_action": selected["action"],
        "confidence": report["confidence"],
        "evidence": [
            {"kind": "risk_metrics", "metrics": risk_state["metrics"]},
            {"kind": "benchmark_selected", "selected": selected},
            {"kind": "market_signal_summary", "summary": report["market_signal_summary"]},
        ],
        "next_steps": report["next_steps"],
        "source_refs": sorted({ref for data in market_data.values() for ref in [data["source_ref"]]}),
        "ranked_decisions": benchmark["ranking"],
        "simulation_results": [
            {"candidate": sim["candidate"], "summary": sim["summary"], "policy_violations": sim["policy_violations"]}
            for sim in simulations
        ],
        "benchmark_comparison": benchmark,
        "policy_violations": risk_state["policy_violations"],
        "market_data_freshness": {symbol: data["freshness"] for symbol, data in market_data.items()},
        "human_review_required": True,
        "review_only": bool((inputs.get("decision_constraints") or {}).get("review_only", True)),
    }


def summarize_risk_state(risk_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "metrics": risk_state["metrics"],
        "policy_violations": risk_state["policy_violations"],
        "weights": risk_state["weights"],
        "source_refs": risk_state["source_refs"],
    }


def market_data_summary(market_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        symbol: {
            "provider": data["provider"],
            "last_price": data["last_price"],
            "last_timestamp": data["last_timestamp"],
            "source_ref": data["source_ref"],
            "freshness": data["freshness"],
        }
        for symbol, data in market_data.items()
    }


def summarize_market_signals(signals: list[Any]) -> str:
    if not signals:
        return "No discretionary market-signal notes were supplied; report relies on market prices and risk metrics."
    return " ".join(str(signal) for signal in signals[:5])[:800]


def artifact_records() -> list[dict[str, Any]]:
    return [
        {
            "artifact_id": "result",
            "type": "result",
            "path": "result.json",
            "producer": "local_run_store",
            "mime_type": "application/json",
            "schema_version": "mn.blueprint.response.v1",
            "source_refs": ["inputs.json", "events.jsonl"],
        },
        {
            "artifact_id": "final_artifact",
            "type": "final_artifact",
            "path": "final_artifact.json",
            "producer": "workflow",
            "mime_type": "application/json",
            "schema_version": "mn.blueprint.final_artifact.v1",
            "source_refs": ["inputs.json", "events.jsonl", "result.json"],
        },
        {
            "artifact_id": "risk_benchmark",
            "type": "benchmark_report",
            "path": "result.json#/benchmark",
            "producer": "workflow",
            "mime_type": "application/json",
            "schema_version": "mn.blueprint.benchmark_report.v1",
            "source_refs": ["events.jsonl"],
        },
    ]


def main(argv: list[str] | None = None) -> None:
    run_blueprint_cli(
        run_blueprint,
        argv,
        description="Run the real-time portfolio risk review advisor blueprint.",
        default_blueprint_id=BLUEPRINT_ID,
    )


if __name__ == "__main__":
    main()
