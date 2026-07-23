# CCTV Operator

`Blueprint ID:` `cctv_operator`

`Category:` `Security`

`Runtime:` `NVIDIA-only service`

CCTV Operator is a stream-only live monitoring service for one approved
RTSP/RTMP source. Version 2 adds live operator steering, adaptive scene
sampling, bounded multimodal frame batches, and an explicit view of the frames
sent to the model.

## Source contract

Set `video_source.uri` to one reachable `rtsp://`, `rtsps://`, `rtmp://`, or
`rtmps://` URI during init review. File and folder sources are rejected.
Visual targets, alert policy, sampling thresholds, output folder, UI port, and
preview enablement remain configurable.

## Adaptive monitoring

The source can remain at its native frame rate for operator preview, but the model never receives that full stream. The default policy:

- keeps one run-scoped FFmpeg camera connection instead of reconnecting for
  each sample;
- inspects a 320-pixel proxy at 1 FPS;
- sends a baseline frame every 20 seconds;
- requires two consecutive proxy changes above the configured threshold;
- collects three seconds of pre-roll and five seconds of post-roll at 5 candidate FPS;
- selects at most ten non-duplicate, temporally diverse frames for one model request; and
- permits one active model request and at most six calls per minute.

Dashboard steering persists only for the current run. “Update watch target” changes the instruction and analyzes immediately by default; “Clear watch target” removes it. Each update receives a command ID and instruction revision so reports identify the instruction used for a batch.

## Runtime requirements

The manifest declares a hard NVIDIA CUDA requirement with one GPU and at least 49,152 MB of GPU or unified IGP memory. Eligibility, including DGX Spark unified-memory accounting, is enforced by `mn-python-sdk`; the blueprint does not duplicate that detection logic. There is no CPU or Mac-only execution path.

Frame preparation runs in one SDK-managed shared
`MirrorNeuron.Runner.DockerWorker` on the selected NVIDIA node. The sampler owns
the exclusive GPU allocation; the detector remains pinned by NVIDIA/CUDA
capabilities and reuses that GPU-enabled container. Reusable capture, scene
scoring, selection, batch persistence, and preview relay mechanics come from
`mirrorneuron-live-video-analysis-skill`; the blueprint retains CCTV steering,
detection, alert, and report policy. The default Nemotron 3 multimodal model
requires the declared 48 GB memory floor.

## Web UI

The blueprint owns a HostLocal `cctv_web_ui` service rendered with
`vercel-labs/json-render` through the generic
`mirrorneuron-web-ui-skill`. It shows:

- an optional browser-safe live preview relay;
- `latest_analyzed_frame.jpg`, labelled by its batch metadata;
- controls for updating or clearing the monitoring instruction; and
- live sampling, backpressure, observation, and report events.

The blueprint service owns `/actions/steer-monitoring`, validates the
CCTV-specific payload, and submits the declared live input directly to Core
over the SDK gRPC client. `mn-api` does not expose a CCTV steering route.
The preview relay is optional and analysis continues if it is unavailable.
Camera credentials remain server-side and are redacted from browser URLs and
events.

## Run and inspect

From the catalog:

```bash
mn blueprint run cctv_operator --web-ui
```

From this folder:

```bash
mn blueprint run --folder . --web-ui
```

Inspect recent state:

```bash
mn blueprint monitor --follow
```

Primary run artifacts under `~/.mn/runs/<run_id>/` are:

- `events.jsonl`
- `cctv_report.json`
- `cctv_report.md`
- `final_artifact.json`
- `web_ui.json`
- `latest_analyzed_frame.jpg`
- `latest_analyzed_frame.json`
- `frame_batches/<batch_id>/batch.json` and selected JPEGs

The output is decision support. A human must confirm any safety, security,
access, or disciplinary response against the original live stream.

## Shared job data

Each configured CCTV job owns persistent `knowledge/`, `databases/rag/`, and
`state/` resources under its stable `job_id`. Manual and scheduled runs share
those resources but retain independent inputs, reports, logs, and status. Run
cleanup never deletes shared resources; reset or deletion is explicit.

## Repository validation

```bash
.venv/bin/python -m pytest -q
```

See [SPEC.md](SPEC.md) for the complete design contract.
