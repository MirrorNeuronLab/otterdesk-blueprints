# Zip Code Property Alpha Engine With Memory

`Blueprint ID:` `finance_zip_code_property_alpha_engine_with_memory`  
`Category:` finance - Finance Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## Intro

Zip Code Property Alpha Engine With Memory is an early MirrorNeuron blueprint for ranking property acquisition opportunities while preserving important facts from noisy historical deal flow. It compares a full-history handoff with an optimized memory packet so evaluators can measure whether memory improves decision quality and reduces context cost.

This README is the short product introduction. The detailed design contract, expected customer outcome, inputs, outputs, memory benchmark, and evaluation criteria live in [SPEC.md](SPEC.md).

## Who It Serves

This blueprint is for real-estate investors, acquisition analysts, property-tech teams, and diligence operators who need decisions to remember more than the latest listing snapshot.

## What It Demonstrates

- Large synthetic property context with distractor deal-flow history.
- Working-memory retrieval with source references.
- Full-context versus optimized-memory benchmark.
- Acquisition action selection among `submit_bid`, `negotiate_discount`, and `watchlist_only`.

## Example Scenario

A current listing snapshot makes one property look attractive, but older facts reveal flood-insurance and roof-risk concerns. The memory packet should preserve those older risks while also connecting positive facts that make a different property the better acquisition target.

## Quick Start

Run a fast deterministic simulation with the fake LLM path:

```bash
cd finance_zip_code_property_alpha_engine_with_memory
python3 payloads/simulation_loop/scripts/run_blueprint.py \
  --mock-llm \
  --steps 3 \
  --runs-root /tmp/mirror-neuron-runs
```

Run the six-step memory benchmark:

```bash
python3 payloads/simulation_loop/scripts/run_blueprint.py \
  --mock-llm \
  --steps 6 \
  --seed 77 \
  --runs-root /tmp/mn-finance-memory-benchmark
```

## Documentation Map

- [SPEC.md](SPEC.md): design details, desired customer outcome, input/output contract, memory benchmark criteria, prototype limits, and upgrade path.
- `manifest.json`: runtime graph, nodes, edges, initial inputs, and metadata.
- `config/default.json`: default identity, memory, benchmark, simulation, LLM, output, logging, and adapter settings.
- `payloads/simulation_loop/`: runnable property simulation and benchmark workflow.

## Prototype Status

This blueprint is a working prototype with synthetic history and benchmark fixtures. It is intended for product evaluation before connecting real listings, broker notes, diligence records, lender constraints, and investment committee outcomes.
