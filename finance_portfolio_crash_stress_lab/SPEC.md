# Portfolio Crash Stress Lab SPEC

## What We Want To Achieve

Build an explainable portfolio stress workflow that shows how risk evolves across a shock and why a defensive action is recommended. The target customer should understand both the final recommendation and the path that led there.

## Customer Problem

Portfolio managers, wealth advisors, risk officers, and fintech evaluators need to understand how a portfolio may behave through a market shock before recommending defensive action. The customer gap is path-dependent risk: drawdown, rate pressure, liquidity, and decisions interact over time, so a one-time summary does not show what happens after an action is applied.

## Design Details

The blueprint runs a deterministic simulation loop. Each step observes portfolio state, asks the stress-test analyst agent to choose from the allowed actions, applies the action effect, records the updated state, and writes a structured report.

The design is intentionally adapter-friendly. The prototype starts with mock scenario inputs, but the same input contract can later receive real holdings, exposures, and policy constraints. The output contract stays centered on a timeline, state deltas, ranked options, and a final risk report.

## Input

The prototype accepts a scenario name, deterministic seed, step count, and starting portfolio state. The core state inputs are initial portfolio value, drawdown percent, rate shock in basis points, and liquidity percent.

The current action space is `rebalance_defensive`, `hedge_rates`, and `raise_cash`. Runtime inputs can come from the bundled mock scenario, inline JSON, file-based JSON, environment JSON, or future real adapters.

For production use, the same contract should be fed by real holdings, asset-class exposures, duration, credit risk, liquidity constraints, tax rules, customer policy limits, and advisor-approved rebalancing options.

## Output: Expected Customer Outcome

The expected customer outcome is an explainable stress report that shows how the portfolio changes through the shock and recommends a defensive action. A useful run returns a timeline of observations and decisions, state deltas, ranked options, and a final portfolio risk report.

The customer should be able to see the recommended action, why it was chosen, what happened to drawdown and liquidity over the simulated path, and which next steps a portfolio team should review before acting.

## Evaluation Criteria

- Action reasonableness: confirm the selected action is plausible for the observed drawdown, rate shock, and liquidity pressure.
- Scenario consistency: verify recommendations change appropriately when the stress scenario, seed, or initial state changes.
- State trajectory: inspect whether drawdown, liquidity, rate shock, and portfolio value move coherently over the decision loop.
- Reproducibility: run with the same seed and mock LLM path and confirm stable results for local evaluation.
- Advisor alignment: compare recommendations with historical decisions, investment committee guidance, or advisor-approved playbooks.
- Explanation quality: check whether the rationale links the action to risk drivers rather than giving a generic recommendation.
- Production readiness: validate against real holdings, customer constraints, market data, and compliance review before any capital allocation decision.

## Result Artifacts To Inspect

Inspect `timeline` for step-by-step observations, LLM decisions, applied actions, and state after each update. Inspect `state_changes` for starting values, ending values, and deltas across portfolio value, drawdown, rate shock, and liquidity.

Inspect `final_artifact` for the recommended action, ranked options, action history, summary, and next steps. When using the local run store, also inspect `run.json`, `config.json`, `inputs.json`, `events.jsonl`, `result.json`, and `final_artifact.json`.

## Prototype Limits

The current blueprint uses mock data and simplified market dynamics for repeatable local runs. It does not model all holdings, taxes, trading costs, compliance constraints, client suitability, or full market microstructure.

The output is a decision-support artifact, not financial advice or an executable trade instruction.

## Upgrade Path To Real Customer Use

Connect portfolio holdings, factor exposures, live or historical market data, liquidity models, and customer-specific policy constraints. Calibrate action effects using historical crisis periods and advisor feedback.

Add approval gates for any client-facing or trade-facing recommendation. Track recommendation quality against backtests, advisor acceptance, realized outcomes, drawdown reduction, liquidity preservation, and compliance review results.
