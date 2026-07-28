# CCTV Operator

`Blueprint ID:` `cctv_operator`

`Category:` `Security`

`Runtime:` `NVIDIA worker; single-node or distributed cluster`

CCTV Operator is a stream-only live monitoring service for one approved
RTSP/RTMP source. Version 2 adds live operator steering, adaptive scene
sampling, bounded multimodal frame batches, and an explicit view of the frames
sent to the model.

## Source contract

Set `video_source.uri` to one reachable `rtsp://`, `rtsps://`, `rtmp://`, or
`rtmps://` URI during init review. File and folder sources are rejected.
Visual targets, alert policy, sampling thresholds, output folder, UI port, and
preview enablement remain configurable. Browsers cannot consume RTSP directly,
so set `web_ui.preview.url` separately to a browser-safe HTTP(S) media URL such
as an HLS playlist.

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
scoring, selection, and batch persistence mechanics come from
`mirrorneuron-live-video-analysis-skill`; the blueprint retains CCTV steering,
detection, alert, and report policy. The default Nemotron 3 multimodal model
requires the declared 48 GB memory floor. Docker Model Runner inference disables
reasoning for this bounded structured-detection call; invalid or reasoning-only
responses surface as analysis failures instead of false “no detection” records.

## Web UI

The blueprint owns a HostLocal `cctv_web_ui` service rendered with
`vercel-labs/json-render` through the generic
`mirrorneuron-web-ui-skill`. It shows:

- an optional browser-safe live preview supplied by the stream gateway;
- `latest_analyzed_frame.jpg`, labelled by its batch metadata;
- controls for updating or clearing the monitoring instruction; and
- live sampling, backpressure, observation, and report events.

The blueprint service owns `/actions/steer-monitoring`, validates the
CCTV-specific payload, and submits the declared live input directly to Core
over the SDK gRPC client. `mn-api` does not expose a CCTV steering route.
The HostLocal UI does not decode or relay media and therefore does not require
FFmpeg. `web_ui.preview.url` points at HLS or another browser-safe HTTP(S) URL
provided by the camera gateway; preview is optional and analysis continues if
it is absent. Camera credentials remain server-side and are redacted from
browser URLs and events. The dashboard derives operator status, latest finding,
confidence, risk, notices, errors, frame counts, sampling trigger, skipped
samples, and model latency from the durable report and latest-frame artifacts.
It does not depend on a per-service `events.jsonl` mirror. The dashboard also
shows the active watch target and accepts a new plain-language monitoring
prompt at any time. Changing
`web_ui.service.host` or `web_ui.service.port` updates both the HostLocal
listener and the runtime's declared service and health-check contract.
The sampler durably writes the current run-scoped instruction to
`monitoring_state.json`, which the dashboard uses as its authoritative watch
target instead of depending on transient event relay files.

## Single-node and multi-node placement

The manifest uses distributed, constraint-based placement. “Distributed” does
not require two computers: with only Spark in the cluster, every workflow node
runs on Spark. In a Mac + Spark cluster, the CUDA-constrained sampler and
detector run on Spark, while the HostLocal report and UI services may run on
either eligible node. Run artifacts and selected-frame references use the
runtime shared-storage data plane, so the report and UI can consume evidence
produced on Spark without embedding node-local absolute paths.

For the simplest single-node deployment, run the command on Spark with its
standalone runtime active.

For the tested Mac-primary + Spark-worker deployment, start the Mac runtime
first and retain the secret token it prints. Stop any standalone runtime on
Spark before starting Spark directly against the Mac primary:

```bash
# On Spark
mn runtime stop
mn runtime start \
  --join-host <mac-ip> \
  --token <main-token> \
  --host <spark-ip>

# On the Mac
mn node join <spark-ip> \
  --local-host <mac-ip> \
  --token <main-token>

mn node list
mn resource list
mn blueprint run --folder ./cctv_operator --web-ui
```

Do not run the worker as an unrelated standalone cluster and then submit work
to it. Restarting with `--join-host` gives both nodes the same cluster
credentials and primary Redis data plane before registration. `mn node list`
must show the Mac and Spark as healthy, and `mn resource list` must show Spark's
NVIDIA/CUDA device, before launch. A healthy two-node run reports
`reliability.mode=multi_node`; the scheduler may still binpack all five
workflow agents on Spark while the Mac owns the job lease.

The cluster token is a secret. Pass it only to the runtime and join commands;
do not store it in blueprint config, logs, or reports.

The submit host validates the stream URI and probes it when local `ffprobe` is
available. If the Mac has no `ffprobe`, reachability is deferred to the
scheduled NVIDIA worker, which owns the actual FFmpeg connection and surfaces
an explicit analysis error if the source cannot be opened.

## Run and inspect

From the catalog:

```bash
mn blueprint run cctv_operator --web-ui
```

Bind the dashboard on all interfaces or choose another port:

```bash
mn blueprint run cctv_operator --web-ui \
  --web-ui-host 0.0.0.0 \
  --web-ui-port 61017
```

Binding `0.0.0.0` exposes the unauthenticated dashboard and its steering
control to reachable peers. Use a firewall or trusted network boundary.

From this folder:

```bash
mn blueprint run --folder . \
  --set video_source.uri=rtsp://camera.example/live \
  --set web_ui.preview.url=https://gateway.example/live/index.m3u8 \
  --web-ui
```

For local development,
`./cctv_operator/scripts/sample_rtsp.sh start` publishes the sample over RTSP
and exposes MediaMTX's HLS proxy. It prints both `--set` values for the run
command.

Inspect recent state:

```bash
mn blueprint monitor --follow
```

Primary run artifacts under `~/.mn/runs/<run_id>/` are:

- `events.jsonl`
- `monitoring_state.json`
- `cctv_report.json`
- `cctv_report.md`
- `final_artifact.json`
- `web_ui.json`
- `latest_analyzed_frame.jpg`
- `latest_analyzed_frame.json`
- `frame_batches/<batch_id>/batch.json` and selected JPEGs

The alert policy is applied to configured target names, model confidence, and
cooldown before creating an operator notice. The default mode is
`human_notice_only`; Slack is attempted only when explicitly enabled and
configured with credentials and a destination.

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
