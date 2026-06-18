# Portfolio Risk Review Assistant

`Blueprint ID:` `portfolio_risk_review_assistant`
`Category:` `Finance`

A portfolio risk co-worker for review-only market and scenario analysis. Give it
holdings, benchmark weights, risk limits, decision constraints, optional market
notes, and an input folder for supporting files; it pulls public market context,
runs risk and simulation math, benchmarks possible actions, and writes risk
summaries and review reports to the output folder.

## What It Does

This blueprint loads a portfolio, fetches public market quote/history data for
the supplied symbols, computes risk features, proposes review-only candidate
actions, simulates each decision with Monte Carlo paths, benchmarks candidates
against no-action, and writes a human-review report.

The LLM is not the risk engine. Deterministic workers handle market data,
returns, covariance, VaR/CVaR, drawdown, concentration, candidate generation,
simulation, scoring, and benchmark ranking. The LLM only summarizes supplied
market-signal notes and turns structured evidence into the final report.

## Quick Start

Run from the catalog:

```bash
mn run portfolio_risk_review_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Inspect recent run state:

```bash
mn blueprint monitor --follow
```

## Inputs And Configuration

- `portfolio`: holdings with `symbol` plus `quantity` or `market_value`.
- `risk_policy`: drawdown, VaR/CVaR, concentration, cash, and turnover limits.
- `decision_constraints`: permitted review-only actions and restricted symbols.
- `market_signals`: optional macro notes or analyst comments for the LLM.
- `benchmark_portfolio`: optional benchmark weights by symbol.
- `examples/sample_inputs/sample_portfolio.json`: synthetic holdings, benchmark, risk policy, constraints, and market-signal pack for demos.

The default configuration uses `public_yahoo_chart` for public market data and
fails closed if required symbols cannot be loaded or are stale. The standard
`mock`, `json`, `file`, and `env_json` adapters are still declared for
blueprint compatibility, but production use should provide real portfolio
inputs through `json`, `file`, or `env_json`.

The live LLM profile is explicit in `config/default.json` as Docker Model Runner `gemma4:e2b`. RAG knowledge now includes a product retrieval playbook for portfolio policy, evidence, and report boundaries.

## Outputs

Runs write artifacts under `~/.mn/runs/<run_id>/`. The main artifact is
`final_artifact.json`, containing ranked decisions, simulation results,
benchmark comparison, policy violations, market data freshness, source refs,
and human-review next steps.

## Safety Checklist

- This blueprint is review-only and must not place trades or send orders.
- Human approval is required before any downstream action.
- Confirm market data freshness and source refs before relying on results.
- Validate tax, mandate, liquidity, and restricted-symbol constraints outside
  the LLM report.
- Keep local customer overrides and portfolio files out of committed defaults.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)
- [Manifest](manifest.json)
- [Default config](config/default.json)

## Validation

Run repository-level tests from `otterdesk-blueprints` after changing catalog
metadata, manifest structure, payload behavior, or shared fixtures:

```bash
.venv/bin/python -m pytest -q
```
