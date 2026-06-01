# Portfolio Risk Review Assistant SPEC

## What We Want To Achieve

Build a review-only real-time portfolio advisor that separates financial
engineering from language generation. The workflow should use public market
data, deterministic risk calculations, Monte Carlo simulation, historical
stress evidence, decision scoring, and benchmark comparison before an LLM writes
the human-facing report.

## Customer Problem

Portfolio risk changes quickly as prices, volatility, liquidity, and macro
signals move. Advisors and portfolio teams need more than a narrative answer:
they need a traceable loop that proposes a decision, simulates that decision,
evaluates it against policy, benchmarks it against doing nothing, and preserves
the evidence for human review.

## Design Details

The blueprint follows the MirrorNeuron blueprint standard with stable identity,
structured inputs, event telemetry, run-store artifacts, and human-control
policy. The workflow stages are:

1. Normalize portfolio, policy, benchmark, and review-only constraints.
2. Fetch public market quote/history data and enforce source freshness.
3. Compute returns, covariance, volatility, beta, VaR, CVaR, drawdown,
   concentration, cash percentage, and policy breaches.
4. Propose candidate decisions such as no action, raise cash, reduce
   concentration, reduce equity beta, duration hedge, and credit-risk reduction.
5. Simulate each candidate with seeded Monte Carlo paths and historical return
   distributions.
6. Benchmark candidates against no-action and policy metrics.
7. Use the LLM only to summarize supplied market signals and write a report
   from structured evidence.

## Input

Required runtime inputs are:

- `portfolio`: holdings with `symbol`, `quantity` or `market_value`, optional
  cost basis, asset class, sleeve, and liquidity tags.
- `risk_policy`: drawdown, VaR/CVaR, concentration, cash, liquidity, and
  turnover limits.
- `decision_constraints`: permitted review-only actions, restricted symbols,
  no-trade assets, tax notes, and mandate constraints.

Optional inputs are `market_signals`, `benchmark_portfolio`,
`poll_seconds`, `simulation_horizon_days`, `monte_carlo_paths`, and `seed`.

The default product path uses public market data through `public_yahoo_chart`.
Mock input remains available only for local validation and demos required by
the shared blueprint standard.

## Output: Expected Customer Outcome

The final artifact should let a reviewer answer:

- Which action was recommended for review?
- How did each candidate perform under Monte Carlo simulation?
- How did the recommendation benchmark against no-action?
- Which policy limits were breached before and after simulation?
- Which market data sources and timestamps supported the result?
- What should a human approve, revise, or reject next?

The artifact is decision support, not financial advice or trade execution.

## Evaluation Criteria

- Real-data readiness: required public market data loads with source refs and
  freshness checks, or the run fails closed.
- Financial engineering quality: returns, covariance, VaR/CVaR, drawdown,
  concentration, beta, and cash metrics are deterministic and testable.
- Decision quality: candidate rankings improve policy fit and risk metrics
  relative to no-action where possible.
- Simulation reproducibility: seeded Monte Carlo runs are deterministic.
- Traceability: recommendations tie back to inputs, market data, events,
  simulations, benchmark rows, and final artifact fields.
- LLM boundary: model output does not create prices, risk metrics, or trades.
- Human review fit: the report clearly marks review-only recommendations and
  next steps.

## Result Artifacts To Inspect

Inspect `events.jsonl` for `market_data_loaded`, `risk_state_computed`,
`decision_candidates_proposed`, `decision_simulated`, `decision_evaluated`,
`benchmark_step_scored`, and `llm_report_written`.

Inspect `result.json` and `final_artifact.json` for ranked candidates,
simulation summaries, benchmark comparison, policy violations, market data
freshness, and source refs.

## Prototype Limits

The v1 public-market adapter is suitable for review and evaluation workflows,
not certified valuation, trade execution, regulated advice, or compliance
approval. Public data can be delayed, stale, adjusted, incomplete, or
unavailable. Customer deployments should validate data licensing, benchmark
definitions, tax constraints, mandate rules, review gates, monitoring, and
retention policies before production use.
