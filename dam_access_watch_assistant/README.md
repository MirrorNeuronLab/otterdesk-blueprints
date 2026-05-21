# Dam Access Watch Assistant

`Blueprint ID:` `dam_access_watch_assistant`  
`Category:` business

## One-line value proposition

Detect and report vehicles entering a dam site from an approved RTSP stream.

## What it is

Dam Access Watch Assistant is a MirrorNeuron blueprint for continuous vehicle-entry monitoring over a dam access camera. It samples an RTSP stream, asks a configurable vision-language model whether vehicles are entering the dam site, records count/type/color/position/movement details, applies cooldown state, and writes reviewable alert artifacts.

## Who this is for

Dam operators, critical-infrastructure security teams, safety operations, and site-access reviewers that need explainable vehicle-entry monitoring without watching every frame.

## Why it matters

Dam access video is continuous and operationally sensitive. A stateful workflow can preserve audit context, suppress duplicate alerts, and keep reviewers in control while still surfacing vehicle entries with useful detail.

## Why this runtime is useful here

The runtime gives this workflow persistent events, local run artifacts, configurable inputs, optional web UI handles, stream declarations, and clean boundaries for OpenShell workers. That makes it easier to connect approved dam camera sources while keeping access decisions inspectable.

## How it works

1. Loads `config/default.json` and any overrides.
2. Resolves the dam video source, VL model endpoint, sampling cadence, and cooldown settings.
3. Samples the default RTSP/H.264 stream over TCP.
4. Emits typed events for frame analysis, vehicle-entry detection, alert decisions, errors, and completion.
5. Writes `result.json`, `final_artifact.json`, `events.jsonl`, and optional dashboard metadata under the local run store.

## Example scenario

A dam access camera is sampled every 10 seconds. The agent checks whether cars or other road vehicles appear to be entering the dam site, reports how many vehicles are visible, their type and color, position in the scene, and movement, then emits an alert payload for review or Slack delivery.

## Inputs

- Video source URI, transport, and codec. The default is `rtsp://9627b0bf2a7b.entrypoint.cloud.wowza.com:1935/app-p5260J38/66abe4b9_stream1`.
- VL model base URL and model name.
- Vehicle-entry confidence threshold, alert cooldown policy, and optional notification destination.
- Mock payloads for deterministic tests.

## Outputs

- Vehicle-entry events emitted when vehicles appear to be entering the dam site.
- Count, type, color, position, movement, and confidence details.
- Alert decisions and notification payloads.
- A final artifact summarizing the run, observations, and recommended next steps.
- Optional shared Gradio or static dashboard metadata in `web_ui.json`.

## How to run

For live video preview, keep the bridge script running while the blueprint is active:

```bash
scripts/start_webcam_stream_for_mac.sh
```

By default it reads the approved Wowza RTSP stream, republishes it to local MediaMTX for browser preview at `http://127.0.0.1:8889/dam-access/`, and uploads rolling frames into the OpenShell detector sandbox so the worker can keep analyzing even when sandbox DNS cannot resolve the upstream RTSP host.

Run the detector script from the blueprint directory:

```bash
python3 payloads/vehicle_detector/scripts/analyze_dam_vehicle_frame.py
```

For a deterministic local smoke test:

```bash
MOCK_VLM_DETECTION=1 python3 payloads/vehicle_detector/scripts/analyze_dam_vehicle_frame.py
```

## How to customize it

Point the stream URI at an approved dam camera or facility RTSP source, tune sampling cadence and alert cooldown, change the VL model endpoint, update vehicle-entry policy text, and connect approved notification output skills. Third-party apps can edit `config/overwrite.json` before launch without changing `config/default.json`.

## What to look for in results

Check whether `events.jsonl` shows frame-analysis events, vehicle-entry decisions, cooldown suppressions, alert delivery attempts, and clean completion. The final artifact should explain what vehicles were observed, what action was selected, and which operator follow-up is recommended.

## Runtime features demonstrated

- Video stream sampling.
- VL model decision path with deterministic mock support.
- Vehicle count, type, color, position, and movement reporting.
- Cooldown state and replayable events.
- OpenShell detector worker isolation.
- Local run store artifacts and optional static dashboard or Gradio dashboard handles.

## Test coverage

The blueprint includes deterministic mock-friendly paths and catalog tests for standard config, manifest metadata, interface channels, run artifacts, and product documentation.

## Limitations

This prototype is for evaluation and customer discovery. It should be reviewed against site policy, privacy rules, model behavior, and notification requirements before connecting real cameras or incident workflows.

## Next steps

Calibrate thresholds against representative dam access footage, add site layout zones and entry-direction rules, connect notification output skills, and tune retention and review policy for production deployments.

## Documentation map

- [SPEC.md](SPEC.md): detailed behavior contract, customer outcome, input/output contract, and upgrade path.
- `manifest.json`: graph, nodes, edges, initial inputs, metadata, stream declarations, and interface contract.
- `config/default.json`: default identity, inputs, streams, LLM, outputs, logging, privacy, budgets, and adapters.
- `config/overwrite.json`: editable local override template.
- `payloads/`: worker code, policies, and supporting runtime assets.
