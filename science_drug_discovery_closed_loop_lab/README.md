# Drug Discovery Closed Loop Lab

`Blueprint ID:` `science_drug_discovery_closed_loop_lab`  
`Category:` science - Science Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## One-line value proposition

Run a long-lived multi-stage drug-discovery loop that keeps generating and evaluating candidates.

## What it is

This blueprint is a reusable MirrorNeuron solution template for a scientific or planning decision where interventions should be tested against an evolving simulated environment. It ships with mock or synthetic inputs so it runs immediately, and it defines a path for replacing those inputs with production data while keeping the same blueprint identity, configuration model, and output contract.

## Who this is for

Computational biology researchers and scientific AI platform evaluators.

## Why it matters

Discovery workflows are iterative: candidate generation, scoring, extraction, and review need to repeat as new evidence arrives. A static dashboard can show the current state, and a one-shot LLM prompt can summarize it, but neither tests what happens after a decision is applied. This blueprint makes the feedback loop visible: state changes, the agent observes it, the agent chooses an action, and the system evolves again.

## Why this runtime is useful here

MirrorNeuron is useful here because it combines LLM reasoning with dynamic system simulation. The agent is placed inside a changing environment instead of outside it as a commentator. Each run has stable identity fields, configurable inputs, structured events, and an auditable final artifact, so teams can compare scenarios, debug decisions, and graduate from mock data to real adapters.

## How it works

1. Load the graph in `manifest.json` and start `target_discovery` with bundled mock inputs.
2. Route work through the agents described by the manifest, using long-running scientific pipeline loop as the evolving system.
3. Let the `Scientific manager and staged worker agents` observe intermediate state, produce decisions or artifacts, and emit typed messages.
4. Preserve execution metadata, logs, and generated artifacts so users can audit what happened.
5. Return candidate artifacts, stage logs, and discovery summaries for review, customization, or downstream workflow integration.

## Example scenario

A pipeline based on BioTarget runs staged workers that manage candidate discovery and result extraction in a continuing loop.

## Inputs

| Input | What it controls | Example | Can customize? |
|---|---|---|---|
| `manifest.json` initial inputs | Sample payloads routed into target_discovery. | `initial_inputs` | Yes |
| `config/default.json` | Standard identity, mock input, LLM, output, logging, and adapter settings. | `outputs.run_root` | Yes |
| Payload fixtures | Bundled synthetic data, policies, scripts, templates, or media used by workers. | `payloads/` or `input/` | Yes |
| Environment variables | Runtime and provider settings for local services or optional integrations. | `MN_LLM_MODEL`, `MN_BLUEPRINT_QUICK_TEST` | Yes |

## Outputs

| Output | What it means | Where to look |
|---|---|---|
| Runtime events | Typed messages and worker events emitted through the manifest graph. | `blueprint_report`, worker-specific events |
| Final artifact | The user-facing candidate artifacts, stage logs, and discovery summaries. | `result.json`, report, alert, or generated artifact |
| Operational logs | Status lines and worker logs for debugging and audit. | `events.jsonl`, runtime logs, worker stderr |
| Generated bundle or payload output | Files produced by bundle generation or specialized workers. | `bundle_summary.json`, `payloads/`, visual artifacts |

## How to run

Run through a registered MirrorNeuron blueprint checkout:

```bash
mn blueprint run science_drug_discovery_closed_loop_lab
```

Inspect registered blueprints and recent run artifacts through the unified CLI:

```bash
mn blueprint list
mn blueprint monitor
```

Run the shared repository tests:

```bash
cd ..
python3 -m pytest -q
```

## How to customize it

Swap target data, scoring functions, candidate generators, stage policies, and stopping criteria.

A practical customization path is:

1. Replace the mock input source with your system of record while preserving the input shape.
2. Calibrate simulation parameters and action effects with historical data or domain experts.
3. Update the LLM agent role, responsibilities, and allowed action schema.
4. Extend `final_artifact` so it matches the report, ticket, plan, or recommendation your team already uses.
5. Connect outputs to the review, approval, alerting, or execution system where real decisions happen.

## What to look for in results

Inspect the manifest-declared output message, worker logs, and generated artifacts. The important question is whether the workflow preserved enough state and evidence for a user to understand why the final result was produced.

The strongest signal is not only the final recommendation. Look for whether the state trajectory, agent rationale, applied actions, and output artifact tell a coherent story that a domain user could review.

## Investor and evaluator narrative

Scientific discovery is a high-value vertical where closed-loop agent workflows can reduce cycle time if connected to validated models and labs. The product lesson is that this is not just a chatbot around data. It is a repeatable pattern for vertical workflows where simulation, state, and agent decisions create a more defensible user experience than static analytics alone.

## Runtime features demonstrated

- long-running loop
- multi-stage pipeline
- scientific workers
- artifact extraction

## Test coverage

The shared test suite verifies manifest loading, standard config sections, mock inputs, deterministic fake LLM execution where applicable, state changes over time, CLI execution for shared runners, run-store artifacts, and structured final outputs. This blueprint is covered by scientific scenario smoke tests, deterministic simulation checks, and structured intervention or experiment output checks. Optional Ollama tests are marked separately so local development stays fast.

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
