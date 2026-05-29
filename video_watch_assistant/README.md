# Video Watch Assistant

`Blueprint ID:` `video_watch_assistant`  
`Category:` business

## One-line value proposition

Detect and report configurable visual targets from an approved RTSP stream.

## What it is

Video Watch Assistant is a MirrorNeuron blueprint for continuous visual monitoring over a video camera. It samples an RTSP stream, asks a configurable vision-language model whether target subjects or activities are visible, records count/category/color/position/activity details, applies cooldown state, and writes reviewable alert artifacts.

## Who this is for

Video operators, facility security teams, safety operations, and site reviewers that need explainable visual detection without watching every frame.

## Why it matters

Continuous video is operationally sensitive. A stateful workflow can preserve audit context, suppress duplicate alerts, and keep reviewers in control while still surfacing configured visual detections with useful detail.

## Why this runtime is useful here

The runtime gives this workflow persistent events, local run artifacts, configurable inputs, optional web UI handles, stream declarations, and clean boundaries for OpenShell workers. That makes it easier to connect approved video stream sources while keeping access decisions inspectable.

## How it works

1. Loads `config/default.json` and any overrides.
2. Resolves the video source, VL model endpoint, sampling cadence, and cooldown settings.
3. Samples the default RTSP/H.264 stream over TCP.
4. Emits typed events for frame analysis, visual detection, operator attention updates, chat-facing human notices, alert decisions, errors, and completion.
5. Writes `result.json`, `final_artifact.json`, `events.jsonl`, and optional dashboard metadata under the local run store.

## Example scenario

A video camera is sampled every 10 seconds. The agent checks whether configured subjects or activities are visible, reports how many detections are present, their label/category/color, position in the scene, and activity, then emits an alert payload for review or Slack delivery.

## Inputs

- Video source URI, transport, and codec. Leave `video_source.uri` as the default mapped endpoint; the pre-launch hook loops the bundled demo video into the selected local RTSP port and passes that runtime URI into validation and the worker.
- VL model base URL and model name.
- Detection confidence threshold, alert cooldown policy, and optional notification destination.
- Optional operator attention requests, such as "pay attention to the red backpack near the left doorway."
- Mock payloads for deterministic tests.

## Outputs

- Visual detection events emitted when configured targets appear in the monitored scene.
- Frame observation summaries that let OtterDesk local AI answer "what happened?" from live run context.
- Chat-facing `human_notice` events when the video changes significantly, such as two people appearing.
- Count, label, category, color, position, activity, and confidence details.
- Alert decisions and notification payloads.
- A final artifact summarizing the run, observations, and recommended next steps.
- Shared Gradio dashboard metadata in `web_ui.json` and Grafana-style layout metadata in `ui.json`.

## How to run

The standard `scripts/pre-launch.sh` hook starts the local mapper before validation and launch. With the default mapped source, it loops `data/sample.mp4` into local MediaMTX and publishes the RTSP stream at the selected local port, usually `rtsp://127.0.0.1:8554/video-watch`. If that port is busy, the hook selects another local port and reports the resolved URI back to the runner. The matching `scripts/post-launch.sh` hook is idempotent cleanup: it stops the recorded ffmpeg/MediaMTX mapper and any matching MediaMTX listeners on the selected RTSP/browser-preview ports after stop, cancel, failed launch, or completed cleanup. It does not open a browser or request webcam access.

The web UI uses the shared blueprint support renderer with a Grafana JSON dashboard model in `config/default.json`. The blueprint only declares panels and event queries; the shared skill renders those panels through Gradio for this blueprint and for non-video blueprints.

Run the detector script from the blueprint directory:

```bash
python3 payloads/visual_detector/scripts/analyze_video_frame.py
```

For a deterministic local smoke test:

```bash
MOCK_VLM_DETECTION=1 python3 payloads/visual_detector/scripts/analyze_video_frame.py
```

## How to customize it

Point the stream URI at an approved video stream or facility RTSP source, tune sampling cadence and alert cooldown, change the VL model endpoint, update the target-detection prompt, and connect approved notification output skills. Third-party apps can edit `config/overwrite.json` before launch without changing `config/default.json`.

## What to look for in results

Check whether `events.jsonl` shows frame-observation summaries, visual detection decisions, chat-facing human notices, cooldown suppressions, alert delivery attempts, and clean completion. The final artifact should explain what was observed, what action was selected, and which operator follow-up is recommended.

## Runtime features demonstrated

- Video stream sampling.
- VL model decision path with deterministic mock support.
- Co-worker conversation context for "what happened?" questions and operator attention requests.
- Human notice events that OtterDesk chat can surface promptly during a running co-worker shift.
- Detection count, label, category, color, position, and activity reporting.
- Cooldown state and replayable events.
- OpenShell detector worker isolation.
- Local run store artifacts and shared Grafana JSON to Gradio dashboard handles.

## Test coverage

The blueprint includes deterministic mock-friendly paths, procedural conversation tests, and catalog tests for standard config, manifest metadata, interface channels, run artifacts, and product documentation.

## Limitations

This prototype is for evaluation and customer discovery. It should be reviewed against site policy, privacy rules, model behavior, and notification requirements before connecting real cameras or incident workflows.

## Next steps

Calibrate thresholds against representative video footage, add site layout zones and entry-direction rules, connect notification output skills, and tune retention and review policy for production deployments.

## Documentation map

- [SPEC.md](SPEC.md): detailed behavior contract, customer outcome, input/output contract, and upgrade path.
- `manifest.json`: graph, nodes, edges, initial inputs, metadata, stream declarations, and interface contract.
- `config/default.json`: default identity, inputs, streams, LLM, outputs, logging, privacy, budgets, and adapters.
- `config/overwrite.json`: editable local override template.
- `payloads/`: worker code, policies, and supporting runtime assets.
