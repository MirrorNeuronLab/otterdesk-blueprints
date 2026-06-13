from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "portfolio_risk_review_assistant" / "payloads" / "simulation_loop" / "scripts" / "run_blueprint.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("portfolio_risk_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeMarketDataClient:
    provider = "fake_public_market"

    def __init__(self, *, stale: bool = False, missing: set[str] | None = None) -> None:
        self.stale = stale
        self.missing = missing or set()

    def history(self, symbol: str, *, range_: str, interval: str, timeout_seconds: float) -> dict:
        del range_, interval, timeout_seconds
        if symbol in self.missing:
            raise RuntimeError(f"missing {symbol}")
        now = int(time.time())
        end = now - (10 * 86400 if self.stale else 3600)
        timestamps = [end - (70 - index) * 86400 for index in range(70)]
        base = {"SPY": 420.0, "AGG": 97.0, "GLD": 185.0}.get(symbol, 100.0)
        wobble = {"SPY": 1.8, "AGG": 0.35, "GLD": 0.9}.get(symbol, 0.5)
        closes = [base + index * wobble + math.sin(index / 3.0) * wobble for index in range(70)]
        return {"timestamp": timestamps, "indicators": {"quote": [{"close": closes}]}}


class FakeLLM:
    provider = "fake"
    model = "fake-report"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict) -> dict:
        self.calls += 1
        if self.calls == 1:
            assert "Do not invent trades" in system_prompt
            assert "benchmark_selected" in user_prompt
        else:
            assert "Act as a domain actor" in system_prompt
        return dict(fallback)


def test_finance_math_helpers_are_deterministic():
    runner = _load_runner()

    assert runner.percent_returns([100, 105, 103.95]) == pytest.approx([0.05, -0.01])
    assert runner.covariance([0.01, 0.02, 0.03], [0.02, 0.04, 0.06]) == pytest.approx(0.0002)

    returns = [-0.10, -0.05, 0.0, 0.02, 0.03]
    assert runner.value_at_risk(returns, 0.80) == pytest.approx(-0.10)
    assert runner.conditional_value_at_risk(returns, 0.80) == pytest.approx(-0.10)
    assert runner.max_drawdown([-0.1, 0.05, -0.2]) == pytest.approx(-0.244)


def test_monte_carlo_candidate_simulation_is_seeded():
    runner = _load_runner()
    now = time.time()
    market = {
        symbol: runner.parse_yahoo_chart(symbol, FakeMarketDataClient().history(symbol, range_="1y", interval="1d", timeout_seconds=1), now=now, stale_after_seconds=259200)
        for symbol in ["SPY", "AGG", "GLD"]
    }
    portfolio = {
        "cash": 50000,
        "holdings": [
            {"symbol": "SPY", "quantity": 100, "market_value": None, "asset_class": "equity", "liquidity": "daily"},
            {"symbol": "AGG", "quantity": 250, "market_value": None, "asset_class": "rates", "liquidity": "daily"},
            {"symbol": "GLD", "quantity": 50, "market_value": None, "asset_class": "commodity", "liquidity": "daily"},
        ],
    }
    monte = {"paths": 200, "horizon_days": 10, "seed": 123}
    risk = {"var_confidence": 0.95, "cvar_confidence": 0.95}
    first = runner.simulate_candidate(portfolio, market, {}, monte, risk)
    second = runner.simulate_candidate(portfolio, market, {}, monte, risk)

    assert first["summary"] == second["summary"]
    assert first["summary"]["paths"] == 200


def test_runner_uses_fake_market_data_and_writes_ranked_review_artifact(tmp_path):
    runner = _load_runner()
    llm = FakeLLM()

    result = runner.run_blueprint(
        llm_client=llm,
        market_data_client=FakeMarketDataClient(),
        runs_root=tmp_path,
        run_id="portfolio-test",
        write_run_store=True,
        config={"llm": {"mode": "fake"}, "market_data": {"stale_after_seconds": 259200}, "monte_carlo": {"paths": 120, "horizon_days": 8, "seed": 7}},
    )

    final = result["final_artifact"]
    assert result["run"]["status"] == "completed"
    expected_actor_count = len(
        json.loads((ROOT / "portfolio_risk_review_assistant" / "config" / "default.json").read_text())["llm"]["agents"]
    )
    assert llm.calls == 1 + expected_actor_count
    assert final["review_only"] is True
    assert final["human_review_required"] is True
    assert set(final["actor_findings"]) == set(
        json.loads((ROOT / "portfolio_risk_review_assistant" / "config" / "default.json").read_text())["llm"]["agents"]
    )
    assert final["llm_usage"]["calls"] == llm.calls
    assert final["ranked_decisions"]
    assert final["simulation_results"]
    assert final["benchmark_comparison"]["baseline"] == "no_action"
    assert {"market_data_loaded", "risk_state_computed", "decision_simulated", "llm_report_written"} <= {
        __import__("json").loads(line)["type"]
        for line in (tmp_path / "portfolio-test" / "events.jsonl").read_text().splitlines()
        if line.strip()
    }


def test_required_market_data_fails_closed_when_stale_or_missing():
    runner = _load_runner()

    with pytest.raises(RuntimeError, match="failed closed"):
        runner.load_market_data(["SPY"], {"stale_after_seconds": 1, "history_range": "1y", "interval": "1d"}, FakeMarketDataClient(stale=True))

    with pytest.raises(RuntimeError, match="missing SPY"):
        runner.load_market_data(["SPY"], {"stale_after_seconds": 259200, "history_range": "1y", "interval": "1d"}, FakeMarketDataClient(missing={"SPY"}))
