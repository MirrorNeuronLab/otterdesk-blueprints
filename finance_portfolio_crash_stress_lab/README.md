# Portfolio Crash Stress Lab

`Blueprint ID:` `finance_portfolio_crash_stress_lab`  
`Category:` finance - Finance Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## Intro

Portfolio Crash Stress Lab is an early MirrorNeuron blueprint for stress-testing a portfolio through drawdown, rate shocks, and liquidity pressure before recommending a defensive action. It demonstrates a decision loop where the portfolio state changes, the agent chooses an action, and the next simulated state reflects that choice.

This README is the short product introduction. The detailed design contract, expected customer outcome, inputs, outputs, and evaluation criteria live in [SPEC.md](SPEC.md).

## Who It Serves

This blueprint is for portfolio managers, wealth advisors, risk officers, and fintech evaluators who need explainable scenario reasoning rather than a one-shot risk summary.

## What It Demonstrates

- Macro shock and portfolio risk simulation.
- LLM-assisted risk report generation.
- Action selection among `rebalance_defensive`, `hedge_rates`, and `raise_cash`.
- Timeline and state-change artifacts for review.

## Example Scenario

A stagflation shock raises rates and drawdown while liquidity falls. The agent observes the simulated portfolio state, recommends a defensive action, and the blueprint records how the state changes after that action.

## Quick Start

Run a fast deterministic simulation with the fake LLM path:

```bash
cd finance_portfolio_crash_stress_lab
python3 payloads/simulation_loop/scripts/run_blueprint.py \
  --mock-llm \
  --steps 3 \
  --runs-root /tmp/mirror-neuron-runs
```

Inspect saved runs:

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py --list-runs
python3 payloads/simulation_loop/scripts/run_blueprint.py --show-run <run_id>
```

## Documentation Map

- [SPEC.md](SPEC.md): design details, desired customer outcome, input/output contract, evaluation criteria, prototype limits, and upgrade path.
- `manifest.json`: runtime graph, nodes, edges, initial inputs, and metadata.
- `config/default.json`: default identity, simulation, LLM, output, logging, and adapter settings.
- `payloads/simulation_loop/`: runnable simulation workflow.

## Prototype Status

This blueprint is a working prototype with mock data and simplified risk dynamics. It is intended for product evaluation before connecting real holdings, risk models, policy constraints, and advisor review workflows.
