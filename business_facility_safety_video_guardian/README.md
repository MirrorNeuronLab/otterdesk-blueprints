# Facility Safety Video Guardian

`Blueprint ID:` `business_facility_safety_video_guardian`  
`Category:` business

## One-line value proposition

Monitor facility video streams, detect visible humans, describe observable appearance and activity, and escalate safety-relevant observations with VL model reasoning.

## What it is

Facility Safety Video Guardian is a MirrorNeuron blueprint for continuous safety monitoring over facility video. It samples a live webcam or RTSP camera stream, asks a configurable vision-language model whether a human is visible, applies cooldown state, and writes reviewable alert artifacts.

## Who this is for

Facilities, security, safety operations, and property management teams that need explainable monitoring without asking people to watch every frame.

## Why it matters

Video monitoring is continuous, noisy, and operationally sensitive. A stateful workflow can preserve audit context, suppress duplicate alerts, and keep human reviewers in control instead of producing a one-shot LLM answer with no durable trail.

## Why this runtime is useful here

The runtime gives this workflow persistent events, local run artifacts, configurable inputs, optional web UI handles, stream declarations, and clean boundaries for OpenShell workers. That makes it easier to connect approved facility sources while keeping safety decisions inspectable.

## How it works

1. Loads `config/default.json` and any overrides.
2. Resolves the video source, VL model endpoint, sampling cadence, and cooldown settings.
3. Samples a live RTSP/H.264 camera stream or browser-published MediaMTX webcam stream.
4. Emits typed events for frame analysis, human detection, alert decisions, errors, and completion.
5. Writes `result.json`, `final_artifact.json`, `events.jsonl`, and optional dashboard metadata under the local run store.

## Example scenario

A front-door camera is sampled every 10 seconds. The agent checks whether a human is visible, describes visible non-identifying appearance details, decides whether the event is alert-worthy, suppresses duplicates during cooldown, and emits an alert payload for review or Slack delivery.

## Inputs

- Video source URI, transport, and codec.
- VL model base URL and model name.
- Alert cooldown policy and optional notification destination.
- Mock payloads for deterministic tests.

## Outputs

- Human detection events emitted only when a person is visible.
- Alert decisions and notification payloads.
- A final artifact summarizing the run, observations, and recommended next steps.
- Optional shared Gradio or static dashboard metadata in `web_ui.json`.

## How to run

Run the detector script from the blueprint directory:

```bash
python3 payloads/person_detector/scripts/analyze_door_camera_frame.py
```

For a local Mac webcam smoke test, start the webcam stream:

```bash
scripts/start_webcam_stream_for_mac.sh
```

## How to customize it

Point the stream URI at an approved webcam or facility RTSP source, tune sampling cadence and alert cooldown, change the VL model endpoint, update safety policy text, and connect approved notification output skills. Third-party apps can edit `config/overwrite.json` before launch without changing `config/default.json`.

## What to look for in results

Check whether `events.jsonl` shows frame-analysis events, human-detection decisions, cooldown suppressions, alert delivery attempts, and clean completion. The final artifact should explain what was observed, what action was selected, and which operator follow-up is recommended.

## Investor and evaluator narrative

This blueprint shows how vertical AI can reason over evolving physical operations state while keeping a durable trail. It can grow from a prototype into a safety operations product by adding richer policy controls, reviewer queues, notification integrations, and customer-managed camera adapters.

## Runtime features demonstrated

- Video stream sampling.
- VL model decision path with deterministic mock support.
- Cooldown state and replayable events.
- OpenShell detector worker isolation.
- Local run store artifacts and optional static dashboard or Gradio dashboard handles.

## Test coverage

The blueprint includes deterministic mock-friendly paths and catalog tests for standard config, manifest metadata, interface channels, run artifacts, and product documentation.

## Limitations

This prototype is for evaluation and customer discovery. It should be reviewed against site policy, privacy rules, model behavior, and notification requirements before connecting real cameras or incident workflows.

## Next steps

Replace the local webcam source with approved facility streams, add human review gates for sensitive alerts, connect notification output skills, and tune privacy rules for production deployments.

## Documentation map

- [SPEC.md](SPEC.md): detailed behavior contract, customer outcome, input/output contract, and upgrade path.
- `manifest.json`: graph, nodes, edges, initial inputs, metadata, stream declarations, and interface contract.
- `config/default.json`: default identity, inputs, streams, LLM, outputs, logging, privacy, budgets, and adapters.
- `config/overwrite.json`: editable local override template.
- `payloads/`: worker code, policies, and supporting runtime assets.
