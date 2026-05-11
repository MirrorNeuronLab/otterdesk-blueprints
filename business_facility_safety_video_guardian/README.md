# Facility Safety Video Guardian

`Blueprint ID:` `business_facility_safety_video_guardian`  
`Category:` business - Business Solution Template  
`Default LLM:` Ollama `nemotron3:33b` with deterministic fake LLM support for tests

## One-line value proposition

Monitor facility video streams and escalate safety-relevant observations with LLM reasoning.

## What it is

This blueprint is a reusable MirrorNeuron solution template for an operating decision where delay, cost, service quality, or revenue can change materially over time. It ships with mock or synthetic inputs so it runs immediately, and it defines a path for replacing those inputs with production data while keeping the same blueprint identity, configuration model, and output contract.

## Who this is for

Facilities, security, safety operations, and property management teams.

## Why it matters

Video monitoring is continuous, noisy, and operationally sensitive; teams need stateful alerts, cooldowns, and explainable observations rather than raw frames. A static dashboard can show the current state, and a one-shot LLM prompt can summarize it, but neither tests what happens after a decision is applied. This blueprint makes the feedback loop visible: state changes, the agent observes it, the agent chooses an action, and the system evolves again.

## Why this runtime is useful here

MirrorNeuron is useful here because it combines LLM reasoning with dynamic system simulation. The agent is placed inside a changing environment instead of outside it as a commentator. Each run has stable identity fields, configurable inputs, structured events, and an auditable final artifact, so teams can compare scenarios, debug decisions, and graduate from mock data to real adapters.

## How it works

1. Load the graph in `manifest.json` and start `ingress` with bundled mock inputs.
2. Route work through the agents described by the manifest, using video stream sampling with alert state as the evolving system.
3. Let the `Safety observation and escalation agent` observe intermediate state, produce decisions or artifacts, and emit typed messages.
4. Preserve execution metadata, logs, and generated artifacts so users can audit what happened.
5. Return detection events, alert decisions, and notification payloads for review, customization, or downstream workflow integration.

## Example scenario

A door-camera stream is sampled, an Ollama-backed agent checks whether a person is visible, and alerts are throttled to avoid noise.

## Inputs

| Input | What it controls | Example | Can customize? |
|---|---|---|---|
| `manifest.json` initial inputs | Sample payloads routed into ingress. | `initial_inputs` | Yes |
| `config/default.json` | Standard identity, mock input, LLM, output, logging, and adapter settings. | `outputs.run_root` | Yes |
| Payload fixtures | Bundled synthetic data, policies, scripts, templates, or media used by workers. | `payloads/` or `input/` | Yes |
| Environment variables | Runtime and provider settings for local services or optional integrations. | `MN_LLM_MODEL`, `MN_BLUEPRINT_QUICK_TEST` | Yes |

## Outputs

| Output | What it means | Where to look |
|---|---|---|
| Runtime events | Typed messages and worker events emitted through the manifest graph. | `blueprint_report`, worker-specific events |
| Final artifact | The user-facing detection events, alert decisions, and notification payloads. | `result.json`, report, alert, or generated artifact |
| Operational logs | Status lines and worker logs for debugging and audit. | `events.jsonl`, runtime logs, worker stderr |
| Generated bundle or payload output | Files produced by bundle generation or specialized workers. | `bundle_summary.json`, `payloads/`, visual artifacts |

## How to run

Generate a quick deterministic bundle for local review:

```bash
cd business_facility_safety_video_guardian
python3 generate_bundle.py --quick-test --output-dir /tmp/mirror-neuron-bundles
```

Then run the generated bundle with your MirrorNeuron runtime entrypoint. Use `config/default.json` and `manifest.json` as the stable contract while replacing bundled fixtures with real data.

Run the shared repository tests:

```bash
cd ..
python3 -m pytest -q
```

## How to customize it

Replace the sample video, tune sampling cadence and alert cooldown, add site-specific safety policies, and connect security notification channels.

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

This illustrates vertical AI for physical operations: agents reason over evolving sensor state and trigger controlled workflows. The product lesson is that this is not just a chatbot around data. It is a repeatable pattern for vertical workflows where simulation, state, and agent decisions create a more defensible user experience than static analytics alone.

## Runtime features demonstrated

- video sampling
- Ollama decision path
- cooldown state
- Slack alerting

## Test coverage

The shared test suite verifies manifest loading, standard config sections, mock inputs, deterministic fake LLM execution where applicable, state changes over time, CLI execution for shared runners, run-store artifacts, and structured final outputs. This blueprint is covered by business scenario smoke tests, mock input paths, and final artifact structure checks. Optional Ollama tests are marked separately so local development stays fast.

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
