# CCTV Operator

`Blueprint ID:` `cctv_operator`

`Category:` `Security`

`Runtime:` `NVIDIA worker; Spark single-node placement`

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
The model endpoint is configured as `host.docker.internal:12434` because the
detector runs in a Docker Worker on Spark; do not change it to `localhost`,
which would point at the worker container rather than the GPU host.

## Web UI

The blueprint owns a HostLocal `cctv_web_ui` service rendered with
`vercel-labs/json-render` through the generic
`mirrorneuron-web-ui-skill`. It shows:

- a browser-safe live preview supplied by the stream gateway, or a blank
  preview surface when no preview URL is configured;
- `latest_analyzed_frame.jpg`, labelled by its batch metadata;
- controls for updating or clearing the monitoring instruction; and
- live sampling, backpressure, observation, and report events.

The blueprint service owns `/actions/steer-monitoring`, validates the
CCTV-specific payload, and submits the declared live input directly to Core
over the SDK gRPC client. `mn-api` does not expose a CCTV steering route.
The HostLocal UI does not decode or relay media and therefore does not require
FFmpeg. `web_ui.preview.url` points at HLS or another browser-safe HTTP(S) URL
provided by the camera gateway; preview is optional, remains blank when absent,
and analysis continues independently. Camera credentials remain server-side
and are redacted from browser URLs and events. The dashboard derives operator
status, latest finding, confidence, risk, notices, errors, frame counts,
sampling trigger, skipped samples, and model latency from the durable report
and latest-frame artifacts.
It does not depend on a per-service `events.jsonl` mirror. The dashboard also
shows the active watch target and accepts a new plain-language monitoring
prompt at any time. Changing
`web_ui.service.host` or `web_ui.service.port` updates both the HostLocal
listener and the runtime's declared service and health-check contract.
The sampler durably writes the current run-scoped instruction to
`monitoring_state.json`, which the dashboard uses as its authoritative watch
target instead of depending on transient event relay files.

When the workflow is scheduled on a remote GPU machine, the report writer and
dashboard are constrained to that same CUDA node. This keeps the UI beside the
run artifacts and avoids a cross-node read of a node-local frame batch. A
wildcard UI listener uses the worker's advertised LAN address when it writes
`web_ui.json`; a browser on the primary computer therefore opens
`http://<spark-ip>:<ui-port>`, not the remote machine's `localhost`.

## Single-node and multi-node placement

The manifest uses constraint-based single-node placement. Spark is selected in
a Mac + Spark cluster because it is the only node meeting the required NVIDIA
CUDA GPU capacity; the sampler, detector, report writer, and UI therefore all
run there. This gives the long-running dashboard and the workers one
authoritative run-artifact directory.

For a Mac-primary + Spark-worker deployment, both cores must use the same
primary Redis coordination store. Start the primary runtime first, then start
Spark as a clean worker with the primary's password-authenticated Redis URL:

```bash
# On Spark
MN_REDIS_URL='redis://:<primary-redis-password>@<mac-ip>:<redis-port>/0' \
MN_REDIS_HA_MODE=single \
MN_REDIS_SENTINELS='' \
MN_REDIS_SENTINEL_HOST_MAP='' \
mn runtime start --worker --host <spark-ip>

# On the Mac
mn node add <spark-ip> --token <spark-worker-token>

mn node list
mn resource show
mn blueprint run ./cctv_operator --web-ui
```

Do not join an unrelated standalone Spark runtime. `mn node add` rejects it
when its coordination-store identity differs from the primary. `mn node list`
must show the Mac and Spark as healthy, and `mn resource show` must show
Spark's NVIDIA/CUDA device before launch.

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

The dashboard listens on all container interfaces by default so the runtime's
published port is reachable. On a remote Spark worker, open the URL shown in
the run's `web_ui.json` (for example, `http://10.0.4.26:61000`) from the Mac.
The launch confirmation can show a submit-host URL, so prefer the URL written
by the dashboard service itself in `web_ui.json` when the scheduled node is
remote. The runtime prepublishes ports `61000` through `61049`; choose
another port in that range when needed:

```bash
mn blueprint run cctv_operator --web-ui \
  --web-ui-port 61017
```

The dashboard and its steering control are unauthenticated and exposed to
peers that can reach the published port. Use a firewall or trusted network
boundary. Set `--web-ui-host 127.0.0.1` only for a genuinely host-local
non-container deployment.

From this folder:

```bash
mn blueprint run . \
  --set video_source.uri=rtsp://camera.example/live \
  --set web_ui.preview.url=https://gateway.example/live/index.m3u8 \
  --web-ui --web-ui-host 0.0.0.0 --web-ui-port 61000
```

For a Spark smoke test, copy this blueprint to Spark (or run the command from a
shared checkout), then start the deterministic source there:

```bash
ssh spark 'cd <blueprint-path> && CCTV_SAMPLE_RTSP_HOST=10.0.4.26 ./scripts/sample_rtsp.sh start'

mn blueprint run . \
  --set video_source.uri=rtsp://10.0.4.26:8554/cctv-sample \
  --set web_ui.preview.url=http://10.0.4.26:8888/cctv-sample/index.m3u8 \
  --web-ui --web-ui-host 0.0.0.0 --web-ui-port 61000
```

The local computer can then open `http://10.0.4.26:61000`. Stop the fixture
with `ssh spark 'cd <blueprint-path> && ./scripts/sample_rtsp.sh stop'`.

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

## Persistent conversation

OtterDesk can ask this hired co-worker about its monitoring role, safe
configuration, schedule, and latest run through the stable read-only job MCP,
even when no CCTV run is active. A question never starts the stream service.

## Repository validation

```bash
python3 -m py_compile \
  payloads/services/cctv_web_ui.py \
  payloads/agents/visual_detector/scripts/analyze_video_frame.py
jq empty manifest.json
jq empty config/default.json
```

Use the launch command above with an explicit `video_source.uri` for runtime
validation; the source contract intentionally rejects the empty default URI.

See [SPEC.md](SPEC.md) for the complete design contract.
