# Portfolio Crash Stress Lab

`Blueprint ID:` `finance_portfolio_crash_stress_lab`  
`Category:` finance - Finance Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## One-line value proposition

Stress a portfolio against drawdown, rate shocks, and liquidity pressure before recommending rebalancing.

## What it is

This blueprint is a reusable MirrorNeuron solution template for a risk or opportunity decision where market conditions, portfolio state, borrower behavior, or claim queues evolve over time. It ships with mock or synthetic inputs so it runs immediately, and it defines a path for replacing those inputs with production data while keeping the same blueprint identity, configuration model, and output contract.

## Who this is for

Portfolio managers, wealth advisors, risk officers, and fintech evaluators.

## Why it matters

Risk changes path-dependently during shocks; one summary cannot show how hedges, cash, and defensive moves alter the next state. A static dashboard can show the current state, and a one-shot LLM prompt can summarize it, but neither tests what happens after a decision is applied. This blueprint makes the feedback loop visible: state changes, the agent observes it, the agent chooses an action, and the system evolves again.

## Why this runtime is useful here

MirrorNeuron is useful here because it combines LLM reasoning with dynamic system simulation. The agent is placed inside a changing environment instead of outside it as a commentator. Each run has stable identity fields, configurable inputs, structured events, and an auditable final artifact, so teams can compare scenarios, debug decisions, and graduate from mock data to real adapters.

## How it works

1. Load mock or adapter-provided inputs for macro shock and portfolio risk simulation.
2. Initialize time-varying state with metrics such as `portfolio_value`, `drawdown_pct`, `rate_shock_bps`, `liquidity_pct`.
3. Advance the environment one step with deterministic seeded drift and volatility.
4. Ask the `Portfolio stress-test analyst` to observe the current state, compare valid actions, and choose among `rebalance_defensive`, `hedge_rates`, `raise_cash`.
5. Apply the selected action back into the simulated system so the next observation changes.
6. Write a structured final artifact for `portfolio risk report` with action history, state deltas, ranked options, and next steps.

## Example scenario

A stagflation shock raises rates and drawdown while liquidity falls, and the agent chooses hedge, cash, or defensive rebalance actions.

## Inputs

| Input | What it controls | Example | Can customize? |
|---|---|---|---|
| `steps` | Scenario control, seed, or domain input. | 5 | Yes |
| `seed` | Scenario control, seed, or domain input. | 42 | Yes |
| `scenario` | Scenario control, seed, or domain input. | "stagflation shock" | Yes |
| `initial_portfolio_value` | Override the starting value for portfolio value. | 1000000 | Yes |
| `initial_drawdown_pct` | Override the starting value for drawdown percent. | 4.0 | Yes |
| `initial_rate_shock_bps` | Override the starting value for rate shock bps. | 60 | Yes |
| `initial_liquidity_pct` | Override the starting value for liquidity percent. | 18 | Yes |

## Outputs

| Output | What it means | Where to look |
|---|---|---|
| `timeline` | Step-by-step observations, LLM decisions, applied actions, and state after each update. | `timeline[0].decision.action` |
| `state_changes` | Start, end, and delta for every simulated metric. | `drawdown_pct: 4.0 -> 6.2` |
| `final_artifact` | The user-facing portfolio risk report and rebalance recommendation. | `recommended_action`, `ranked_options`, `next_steps` |
| `llm` | Provider, model, call count, and fallback metadata for the agent path. | `ollama/nemotron3:33b` or fake test client |
| Run directory | Auditable artifacts written under the global run store. | `run.json`, `events.jsonl`, `result.json` |

## How to run

Run a fast deterministic simulation with the fake LLM path:

```bash
cd finance_portfolio_crash_stress_lab
python3 payloads/simulation_loop/scripts/run_blueprint.py \
  --mock-llm \
  --steps 3 \
  --runs-root /tmp/mirror-neuron-runs
```

Run the same blueprint against Ollama:

```bash
MN_LLM_API_BASE=http://192.168.4.173:11434 \
MN_LLM_MODEL=ollama/nemotron3:33b \
python3 payloads/simulation_loop/scripts/run_blueprint.py --steps 3
```

Inspect saved runs:

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py --list-runs
python3 payloads/simulation_loop/scripts/run_blueprint.py --show-run <run_id>
```

Run the shared repository tests:

```bash
cd ..
python3 -m pytest -q
```

## How to customize it

Connect holdings, factor exposures, risk models, macro scenarios, tax constraints, and policy limits.

A practical customization path is:

1. Replace the mock input source with your system of record while preserving the input shape.
2. Calibrate simulation parameters and action effects with historical data or domain experts.
3. Update the LLM agent role, responsibilities, and allowed action schema.
4. Extend `final_artifact` so it matches the report, ticket, plan, or recommendation your team already uses.
5. Connect outputs to the review, approval, alerting, or execution system where real decisions happen.

## What to look for in results

Inspect `timeline` to see each observation and decision, `state_changes` to verify the simulated `drawdown_pct` and `liquidity_pct` moved over time, and `final_artifact` to review the recommended action and ranked allocation sleeve options.

The strongest signal is not only the final recommendation. Look for whether the state trajectory, agent rationale, applied actions, and output artifact tell a coherent story that a domain user could review.

## Investor and evaluator narrative

Asset-management risk copilots are commercially attractive because decisions are high-value and require explainable scenario reasoning. The product lesson is that this is not just a chatbot around data. It is a repeatable pattern for vertical workflows where simulation, state, and agent decisions create a more defensible user experience than static analytics alone.

## Runtime features demonstrated

- macro shock simulation
- portfolio risk
- LLM risk report
- decision feedback

## Test coverage

The shared test suite verifies manifest loading, standard config sections, mock inputs, deterministic fake LLM execution where applicable, state changes over time, CLI execution for shared runners, run-store artifacts, and structured final outputs. This blueprint is covered by finance scenario smoke tests, deterministic mock LLM tests, and structured risk or opportunity output checks. Optional Ollama tests are marked separately so local development stays fast.

## Limitations

- Mock data and simplified dynamics are included for repeatable local runs.
- Outputs are decision-support artifacts, not production advice.
- Domain assumptions should be validated before connecting real systems or acting on recommendations.
- Specialized worker blueprints may require the MirrorNeuron runtime or optional local services to execute the full graph.

## Next steps

- Connect a real data adapter and keep the input contract stable.
- Add scenario comparison, dashboards, or persisted memory for repeated runs.
- Add human approval gates for high-impact actions.
- Track evaluation metrics that compare simulated recommendations against known outcomes.
- Move operational logs and final artifacts into your team's normal review workflow.
