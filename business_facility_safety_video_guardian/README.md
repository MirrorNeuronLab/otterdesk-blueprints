# Facility Safety Video Guardian

`Blueprint ID:` `business_facility_safety_video_guardian`  
`Category:` business - Business Solution Template  
`Default Video Source:` local RTSP/H.264 stream at `rtsp://127.0.0.1:8554/local-camera`  
`Default VL Model:` Ollama `nemotron3:33b` at `http://192.168.4.173:11434` with deterministic mock support for tests

## Intro

Facility Safety Video Guardian is an early MirrorNeuron blueprint for monitoring facility video streams and escalating safety-relevant observations. It demonstrates how an agent can watch sampled video state, reason over whether a human face is visible, describe observable facial appearance, apply alert cooldown logic, and produce reviewable notification payloads.

This README is the short product introduction. The detailed design contract, expected customer outcome, inputs, outputs, and evaluation criteria live in [SPEC.md](SPEC.md).

## Who It Serves

This blueprint is for facilities, security, safety operations, and property management teams that need help reducing manual monitoring burden without losing reviewability.

## What It Demonstrates

- Video stream sampling for a door or facility camera.
- Configurable camera source, defaulting to a local RTSP/H.264 stream.
- Human face detection and observable facial appearance description through a configurable VL model endpoint or deterministic mock mode.
- Cooldown-aware alert decisions to avoid notification noise.
- Structured events and artifacts that a human reviewer can audit.

## Example Scenario

A front-door camera is sampled every few seconds. The agent checks whether a human face is visible, describes visible non-identifying facial appearance details, decides whether the event is alert-worthy, suppresses duplicates during cooldown, and emits an alert payload for review or Slack delivery.

## Quick Start

Generate a quick deterministic bundle for local review:

```bash
cd business_facility_safety_video_guardian
python3 generate_bundle.py --quick-test --output-dir /tmp/mirror-neuron-bundles
```

Then run the generated bundle with the MirrorNeuron runtime entrypoint.

Use a live VL model by overriding the endpoint and model name:

```bash
python3 generate_bundle.py \
  --video-source-uri rtsp://127.0.0.1:8554/local-camera \
  --video-source-transport rtsp \
  --video-source-codec h264 \
  --vl-model-base-url http://192.168.4.173:11434 \
  --vl-model-name nemotron3:33b
```

For bundled demo media instead of a live camera, pass `--video-source-uri samples/door-demo.mp4`. The detector also honors `VIDEO_SOURCE_URI`, `VIDEO_SOURCE_TRANSPORT`, `VIDEO_SOURCE_CODEC`, `VL_MODEL_BASE_URL`, and `VL_MODEL_NAME` at runtime. Existing `OLLAMA_BASE_URL` and `OLLAMA_MODEL` environment variables still work as compatibility aliases.

Third-party apps can edit or replace `config/overwrite.json` before launch to override the video source and VL model settings without changing `config/default.json`. Runtime should load `config/default.json` first, then deep-merge `config/overwrite.json` when present; direct runtime environment variables may still override the resolved config if the runner supports them.


## Web UI

This blueprint includes a local static web UI at `payloads/web_ui/index.html`. It is registered through the shared `mn_blueprint_support.web_ui` contract by `payloads/web_ui/register_dashboard.py`, which writes `web_ui.json` with a `WebUIHandle`. The dashboard shows the camera or demo video stream beside detector events such as `door_camera_frame_analyzed`, `door_camera_face_detected`, alert delivery, and frame-analysis failures.

Open it directly for bundled demo media, or pass query parameters for a served video and event feed:

```text
payloads/web_ui/index.html?video=../person_detector/samples/door-demo.mp4&events=/path/to/events.jsonl
```


Register the dashboard for a run store directory with the shared support code:

```bash
python3 payloads/web_ui/register_dashboard.py --run-id <run_id>
```

Browsers usually cannot play raw RTSP URLs directly. For live review, expose the RTSP camera as browser-playable HLS, MP4, or WebRTC and pass that URL as `video`. If direct event polling is blocked by browser file/CORS rules, use the Events file control with the run store `events.jsonl`.

## Documentation Map

- [SPEC.md](SPEC.md): design details, desired customer outcome, input/output contract, evaluation criteria, prototype limits, and upgrade path.
- `manifest.json`: runtime graph, nodes, edges, initial inputs, and metadata.
- `config/default.json`: default identity, inputs, LLM, output, logging, and adapter settings.
- `config/overwrite.json`: editable third-party override template for video source and VL model settings.
- `payloads/`: bundled worker code, demo media, and supporting runtime assets.

## Prototype Status

This blueprint is a working prototype with mock-friendly execution paths. It is intended for product evaluation and customer discovery before connecting real cameras, incident workflows, and production safety policies.
