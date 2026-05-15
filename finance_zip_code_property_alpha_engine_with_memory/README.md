# Zip Code Property Alpha Engine With Memory

`Blueprint ID:` `finance_zip_code_property_alpha_engine_with_memory`  
`Category:` finance - Finance Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## One-line value proposition

Rank property acquisition opportunities with working memory over noisy ZIP-code history, broker flow, financing constraints, and prior decision outcomes.

## What it is

This blueprint extends the ZIP-code property alpha scenario with a working-memory layer and an explicit benchmark. The simulation creates a large historical context of broker notes, rent comps, permits, lender notes, insurance quotes, and operations messages. Most of that context is noisy; a small set of old facts is critical for the correct acquisition recommendation.

The run compares two handoff strategies: simply sharing the full agent history, like a long chat transcript, versus passing an optimized memory packet. The full-history path keeps everything but pays the token and attention cost. The optimized path retrieves source-grounded facts, connects them across agents, and records whether it preserves or improves decision quality with much less context.

## Who this is for

Real-estate investors, acquisition analysts, property-tech teams, and diligence operators who need decisions to remember more than the latest listing snapshot.

## Why it matters

Property acquisition decisions often depend on older broker, lender, rent, insurance, and diligence facts that disappear inside large noisy deal flow. A static dashboard can show current market numbers, and a one-shot LLM prompt can summarize a visible slice, but neither reliably preserves the old facts that change the bid decision. Working memory makes those facts available again with provenance.

## Why this runtime is useful here

MirrorNeuron is useful here because it runs an LLM decision loop inside a changing environment and records the consequences. This variant adds memory retrieval and benchmark scoring, so evaluators can inspect not just what the agent recommended, but whether the memory layer beats full-context sharing on cost, speed, and decision quality. It still keeps the standard blueprint identity, config, run store, static dashboard, and fake LLM test path.

## How it works

1. Load mock or adapter-provided inputs for the target ZIP code and memory settings.
2. Seed a large synthetic deal-flow history across the target ZIP and distractor ZIPs.
3. Preserve critical source facts about transit, hiring, rent upside, DSCR exceptions, seller motivation, inspection risk, flood insurance, and roof issues.
4. Advance market state over repeated steps with deterministic drift and volatility.
5. Build a noisy current observation window that hides some older critical facts.
6. Compile a full-history baseline packet that simulates replaying all agent context into the next handoff.
7. Retrieve a compact optimized memory packet with stable `source_refs`.
8. Produce both a full-history baseline decision and an optimized-memory decision.
9. Score both decisions on action accuracy, property match, critical fact recall, risk awareness, total quality, token use, and estimated latency.
10. Apply the selected action back into the simulated system and write a final artifact with benchmark results.

## Example scenario

The current snapshot makes Ivy Duplex look attractive because it is cheaper, while older memory contains flood-insurance and roof-risk facts that should penalize it. The same memory also connects River Quad's rent upside, DSCR exception, motivated seller, and clean inspection, making `submit_bid` on River Quad the higher-quality action.

## Inputs

| Input | What it controls | Example | Can customize? |
|---|---|---|---|
| `steps` | Number of decision loop iterations. | 6 | Yes |
| `seed` | Deterministic simulation seed. | 77 | Yes |
| `target_zip` | ZIP code being evaluated. | `"02139"` | Yes |
| `max_price` | Price ceiling for acquisition decisions. | 950000 | Yes |
| `memory_mode` | Whether the applied action uses memory or the baseline. Use `compare`, `on`, or `off`. | `"compare"` | Yes |
| `history_months` | Size of the generated historical context. | 24 | Yes |
| `noise_events_per_month` | Deal-flow noise per ZIP per month. | 10 | Yes |
| `memory_limit` | Maximum facts selected into the memory packet. | 36 | Yes |
| `all_context_token_budget` | Budget used to simulate full-history context-window pressure. | 8000 | Yes |
| `all_context_attention_limit` | Effective number of facts the full-history baseline can actively use. | 36 | Yes |
| `initial_median_price_index` | Override the starting value for median price index. | 112 | Yes |
| `initial_demand_index` | Override the starting value for buyer demand index. | 67 | Yes |
| `initial_cap_rate_pct` | Override the starting estimated cap rate percent. | 5.45 | Yes |
| `initial_risk_score` | Override the starting market risk score. | 58 | Yes |
| `initial_liquidity_score` | Override the starting liquidity score. | 47 | Yes |
| `initial_rent_growth_signal` | Override the starting rent-growth signal. | 4.1 | Yes |

## Outputs

| Output | What it means | Where to look |
|---|---|---|
| `timeline` | Step-by-step observations, memory packets, decisions, and state updates. | `timeline[0].memory_packet` |
| `memory_comparison` | Full-history decision, optimized-memory decision, oracle, and per-step quality scores. | `timeline[0].memory_comparison` |
| `context_packets` | Full-history context summary and optimized memory packet for the same step. | `timeline[0].context_packets` |
| `benchmark` | Aggregate quality and efficiency metrics for full-context sharing versus optimized memory. | `benchmark.lift.estimated_token_reduction_ratio` |
| `state_changes` | Start, end, and delta for every simulated metric. | `cap_rate_pct`, `risk_score` |
| `final_artifact` | User-facing acquisition recommendation, ranked options, benchmark, and next steps. | `recommended_action`, `ranked_options` |
| `llm` | Provider, model, call count, and fallback metadata for the agent path. | `ollama/nemotron3:33b` or fake test client |
| Run directory | Auditable artifacts written under the global run store. | `run.json`, `events.jsonl`, `result.json` |

## How to run

Run a fast deterministic simulation with the fake LLM path:

```bash
cd finance_zip_code_property_alpha_engine_with_memory
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

## How to run the benchmark

The default benchmark compares two handoff modes in the same run:

- `all_context`: memory layer disabled; the next agent receives the full prior agent history.
- `optimized_memory`: memory layer enabled; the next agent receives the optimized memory packet.

Run the deterministic six-step benchmark:

```bash
cd finance_zip_code_property_alpha_engine_with_memory
python3 payloads/simulation_loop/scripts/run_blueprint.py \
  --mock-llm \
  --steps 6 \
  --seed 77 \
  --runs-root /tmp/mn-finance-memory-benchmark \
  > /tmp/mn-finance-memory-benchmark-result.json
```

Print the main benchmark metrics:

```bash
python3 - <<'PY'
import json
from pathlib import Path

result = json.loads(Path("/tmp/mn-finance-memory-benchmark-result.json").read_text())
benchmark = result["benchmark"]
print(json.dumps({
    "schema_version": benchmark["schema_version"],
    "all_context": benchmark["all_context"],
    "optimized_memory": benchmark["optimized_memory"],
    "lift": benchmark["lift"],
    "quality_gate": benchmark["quality_gate"],
    "recommended_action": result["final_artifact"]["recommended_action"],
    "recommended_property_id": result["final_artifact"]["recommended_property_id"],
}, indent=2, sort_keys=True))
PY
```

Run with the memory layer disabled for the applied action while still scoring both benchmark arms:

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py \
  --mock-llm \
  --steps 6 \
  --seed 77 \
  --input-json '{"memory_mode":"off"}' \
  --runs-root /tmp/mn-finance-memory-benchmark-off
```

Stress a larger context:

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py \
  --mock-llm \
  --steps 6 \
  --seed 77 \
  --input-json '{"history_months":48,"noise_events_per_month":20,"memory_limit":36}' \
  --runs-root /tmp/mn-finance-memory-benchmark-large
```

The most important fields are `benchmark.all_context.mean_estimated_input_tokens`, `benchmark.optimized_memory.mean_estimated_input_tokens`, `benchmark.lift.estimated_token_reduction_ratio`, and `benchmark.lift.quality_score_delta`.

Run the shared repository tests:

```bash
cd ..
python3 -m pytest -q
```

## How to customize it

Replace the synthetic history with MLS exports, county records, broker notes, rent comps, lender constraints, inspection summaries, insurance quotes, and prior decision outcomes. Keep the input shape stable, then tune the memory fact importance, retrieval tags, scoring weights, and oracle fixtures to match your acquisition process.

A practical customization path is:

1. Replace generated facts with your deal-flow and diligence feeds.
2. Mark critical facts with stable IDs and `source_refs`.
3. Calibrate action effects and quality scoring against historical investment committee decisions.
4. Update the LLM role, responsibilities, and allowed action schema.
5. Connect outputs to review, approval, alerting, or investment memo systems.

## What to look for in results

Start with `benchmark.optimized_memory.mean_quality_score` and `benchmark.all_context.mean_quality_score`, then check `benchmark.lift.estimated_token_reduction_ratio`. A healthy run should show the optimized memory path preserving decision quality while using far fewer estimated tokens than full-history context sharing.

Then inspect `timeline[*].context_packets` to compare the full-history packet against the optimized memory packet, and check `timeline[*].memory_packet.source_refs` to verify the compact packet kept the older facts that justify the decision.

## Investor and evaluator narrative

This is a credible vertical AI wedge for real-estate investors because it turns large unstructured deal flow into source-grounded acquisition decisions. The product lesson is that memory is not decoration. It can be measured as decision-quality lift when older facts change the action.

## Runtime features demonstrated

- large synthetic finance context
- working memory retrieval
- source refs
- decision quality benchmark
- full-context baseline
- optimized memory comparison
- LLM investment reasoning

## Test coverage

The shared test suite verifies manifest loading, standard config sections, mock inputs, deterministic fake LLM execution where applicable, state changes over time, CLI execution, run-store artifacts, and structured final outputs. This blueprint adds focused contract coverage for the memory benchmark schema, critical source refs, large-context fixture size, full-context budget pressure, and optimized-memory token reduction. Optional Ollama tests are marked separately so local development stays fast.

## Limitations

- Mock data and simplified dynamics are included for repeatable local runs.
- Outputs are decision-support artifacts, not production advice.
- The oracle is a benchmark fixture, not a guarantee of real-world return.
- Domain assumptions should be validated before connecting real systems or acting on recommendations.
- The current memory layer is in-blueprint and synthetic; production deployments should connect real memory storage and access controls.

## Next steps

- Connect a real data adapter and keep the input contract stable.
- Replace synthetic memory facts with broker, lender, insurance, rent, and diligence event streams.
- Add human approval gates for capital-committing actions.
- Track benchmark metrics against known acquisition outcomes.
- Move operational logs and final artifacts into the team's normal review workflow.
