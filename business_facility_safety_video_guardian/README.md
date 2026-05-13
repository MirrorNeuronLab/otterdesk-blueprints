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

For Docker-backed local runs with the detector in OpenShell, `config/overwrite.json` points the detector at sandbox-local `/sandbox/live/latest.jpg`. The Mac webcam script keeps MediaMTX publishing on the host and uploads a rolling `latest.jpg` frame into the detector OpenShell sandbox, so detection uses the live Mac camera without adding OpenCV or ffmpeg to the core Docker image.

The detector runs in its own OpenShell sandbox, not in the core Docker image. The `person_detector` node declares `custom_openshell_image: "person_detector/openshell_sandbox"`, which points at `payloads/person_detector/openshell_sandbox`; that Dockerfile installs ffmpeg and OpenCV with apt inside only the detector sandbox image. Other OpenShell agents can declare their own `custom_openshell_image` values, and agents without that field use the default OpenShell environment. Deleting or stopping the job removes the shared OpenShell sandbox and its ports/resources without adding OpenCV or ffmpeg to MirrorNeuron core Docker.

For a local Mac webcam smoke test, start MediaMTX and publish from the browser:

```bash
scripts/start_demo_camera_stream_for_mac.sh
```

The script opens the MediaMTX webcam publisher at `http://127.0.0.1:8889/local-camera/publish` with H.264 video and audio disabled. Allow camera access and click Publish; the detector reads live frames uploaded to `/sandbox/live/latest.jpg` inside its OpenShell sandbox, while the dashboard preview reads `http://127.0.0.1:8889/local-camera/`. For a deterministic file-backed stream, use:

```bash
VIDEO_FILE=payloads/person_detector/samples/door-demo.mp4 scripts/start_demo_camera_stream_for_mac.sh
```


## Web UI

This blueprint uses the shared Gradio dashboard from `mn_blueprint_support.gradio_dashboard`. `mn run` launches that support module for the blueprint, and the module writes `ui.json` and `web_ui.json` into `~/.mn/runs/<run_id>`.

```text
~/.mn/runs/<run_id>/web_ui.json
```

Start MirrorNeuron services before running the blueprint:

```bash
mn start
```

Open the URL recorded in `web_ui.json`. The shared dashboard reads this blueprint's run store configuration, shows one merged Video Source area, links the browser webcam publisher, embeds the MediaMTX WebRTC preview for live streams, and polls detector events such as `door_camera_frame_analyzed`, `door_camera_face_detected`, alert delivery, and frame-analysis failures.

Browsers usually cannot play raw RTSP URLs directly. For local live review, the default dashboard uses MediaMTX's WebRTC pages: `http://127.0.0.1:8889/local-camera/publish` for webcam publishing and `http://127.0.0.1:8889/local-camera/` for playback.

## Documentation Map

- [SPEC.md](SPEC.md): design details, desired customer outcome, input/output contract, evaluation criteria, prototype limits, and upgrade path.
- `manifest.json`: runtime graph, nodes, edges, initial inputs, and metadata.
- `config/default.json`: default identity, inputs, LLM, output, logging, and adapter settings.
- `config/overwrite.json`: editable third-party override template for video source and VL model settings.
- `payloads/`: bundled worker code, demo media, and supporting runtime assets.

## Prototype Status

This blueprint is a working prototype with mock-friendly execution paths. It is intended for product evaluation and customer discovery before connecting real cameras, incident workflows, and production safety policies.
