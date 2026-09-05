# CCTV Operator

`Blueprint ID:` `cctv_operator`

`Category:` `Security`

`Runtime:` `NVIDIA worker; constraint-routed to Spark in a Mac + Spark cluster`

CCTV Operator is a stream-only live monitoring service with a self-contained
demo stream and support for one approved external RTSP/RTMP source. Version
3.1 puts the looping test video, MediaMTX server, FFmpeg publisher, workflow
executors, report writer, and Web UI inside DockerWorkers, so
the default demo needs no camera URL or host-side media tools. Its read-only
operations console serves a CUDA-assisted MJPEG preview and server-sent operator
events without exposing the camera URI to the browser. Visual analysis
uses the cataloged `nemotron3:q4_K_M` Docker Model Runner artifact through the
node-local LiteLLM proxy.

## Source contract

The default `video_source.profile=bundled_demo` starts MediaMTX and a looping
sample publisher inside the DockerWorker, then monitors
`rtsp://127.0.0.1:8554/cctv-demo`. Launch validation recognizes this explicit
profile and leaves its reachability check to the worker that owns it.

For a real camera, set `video_source.profile=external` and set
`video_source.uri` to one reachable `rtsp://`, `rtsps://`, `rtmp://`, or
`rtmps://` URI. File and folder sources are rejected. The Web UI relays this
server-side source as MJPEG, so browsers never receive the RTSP/RTMP URI or its
credentials.

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

Monitoring steering persists only for the current run. The external OtterDesk
chat AI sends the declared `steer_monitoring` live input over the blueprint MCP;
the dashboard is intentionally read-only. Each update receives a command ID and
instruction revision so reports identify the instruction used for a batch.

## Runtime requirements

The manifest declares a hard NVIDIA CUDA requirement with one GPU and at least 49,152 MB of GPU or unified IGP memory. Eligibility, including DGX Spark unified-memory accounting, is enforced by `mn-python-sdk`; the blueprint does not duplicate that detection logic. There is no CPU or Mac-only execution path.

All executable CCTV components use SDK-managed
`MirrorNeuron.Runner.DockerWorker` containers on the selected NVIDIA node. The
sampler owns the exclusive GPU allocation; ingress, detector, and report writer
reuse that GPU-enabled container. The Web UI also runs in that shared
host-network DockerWorker. The generic Web UI skill binds an OS-selected free
port, and the browser reaches it through the standard job-scoped Web UI proxy without a
host-side UI process or a second transfer of the bundled video. In bundled demo
mode, the shared media container starts the pinned
MediaMTX server and loops the bundled sample with FFmpeg before sampling begins.
Reusable capture, scene
scoring, selection, and batch persistence mechanics come from
`mirrorneuron-live-video-analysis-skill`; the blueprint retains CCTV steering,
detection, alert, and report policy. The default Nemotron 3 multimodal model
requires the declared 48 GiB (49,152 MB) memory floor. The blueprint declares
the cataloged `nemotron3:q4_K_M` artifact with the Docker Model Runner provider.
Submission defers its installation, then the first detector call prepares it on
the selected node with `docker model pull nemotron3:q4_K_M`, registers the
model, and refreshes the node's LiteLLM route. The detector then calls that
LiteLLM route; it never calls Docker Model Runner directly or installs a model
on the submit host. Inference disables reasoning for this bounded structured-
detection call; invalid or reasoning-only responses surface as analysis failures
instead of false “no detection” records.

## Web UI

The blueprint owns a DockerWorker `cctv_web_ui` service and its browser page.
It claims the bound service through `mirrorneuron-web-ui-skill`, which only
writes the durable iframe-proxy handle. It shows:

- a stable multipart MJPEG preview produced by one shared FFmpeg relay using
  CUDA decode and `scale_cuda` inside the NVIDIA DockerWorker;
- `latest_analyzed_frame.jpg`, labelled by its batch metadata;
- an auto-updating, newest-first operator event stream over SSE; and
- live sampling, backpressure, observation, report, and review telemetry.

The UI exposes no steering form or browser action. External chat/MCP clients use
the manifest-declared `steer_monitoring` live input; callers still cannot name
physical agents or routes. The UI process opens the configured stream once and
fans its MJPEG frames out to connected browsers. FFmpeg uses CUDA hardware
decode and resize; because NVIDIA FFmpeg does not provide an MJPEG NVENC codec,
the final JPEG entropy encoding uses FFmpeg's MJPEG encoder. There is no CPU
decode fallback. Camera credentials remain server-side and are redacted from
browser URLs, events, and errors. The dashboard derives operator
status, latest finding, confidence, risk, notices, errors, frame counts,
sampling trigger, skipped samples, and model latency from the durable report
and latest-frame artifacts.
It does not depend on a per-service `events.jsonl` mirror. The dashboard also
shows the active watch target supplied through chat. The default
`web_ui.service.port` value is `0`.
The generic Web UI skill resolves a runtime-reserved port when one exists;
otherwise CCTV binds port `0` and claims the actual OS-selected port. CCTV does
not maintain a port range or allocator.
The sampler durably writes the current run-scoped instruction to
`monitoring_state.json`, which the dashboard uses as its authoritative watch
target instead of depending on transient event relay files.

When the workflow is scheduled on a remote GPU machine, ingress, analysis,
report writing, and the dashboard stay in DockerWorkers on that same CUDA node.
The UI's dedicated container shares the runtime artifact volume with the media
worker, avoiding a cross-node read of a node-local frame batch. A
wildcard UI listener uses the worker's execution-node address when it writes
the private upstream into `web_ui.json`. The browser opens only the stable
`http://localhost:55173/jobs/<job_id>/ui` route and never navigates to the
worker address or allocated port.

## Constraint-based federated placement

The manifest uses `single_node`, constraint-based placement. Spark is the only
eligible job owner in a Mac + Spark federation because it is the only node
meeting the required NVIDIA CUDA GPU capacity. The SDK therefore forwards the
whole job to Spark's Core and pins the sampler, detector, report writer, and UI
there. This gives the long-running dashboard and workers one authoritative
run-artifact directory while the Mac remains the control plane.

The special multimodal model is lazily installed on first detector use. Its
preparation progress is shown in the run activity. To inspect the completed
installation on Spark:

```bash
ssh spark 'docker model ls'
```

The DMR inventory will include `nemotron3:q4_K_M`, and the node's LiteLLM
inventory will expose that same short model name. A text-only model such as
`nemotron-3.5-lightning:latest` does not satisfy this blueprint.

For a Mac-primary + Spark deployment, each federated Core must have its own
writable Redis coordination store. Start an independent runtime on Spark, then
add it from the Mac using the token printed by Spark:

```bash
# On Spark
mn runtime start --host <spark-ip>

# On the Mac
mn node add <spark-ip> --token <spark-runtime-token>

mn node list
mn resource show
mn blueprint run ./cctv_operator --web-ui
```

Do not point Spark at the Mac's Redis. Federation requires distinct store
identities, and `mn node add` rejects two runtimes that share one. `mn node
list` must show the Mac and Spark as healthy, and `mn resource show` must show
Spark's NVIDIA/CUDA device before launch.

The cluster token is a secret. Pass it only to the runtime and join commands;
do not store it in blueprint config, logs, or reports.

The submit host accepts the fixed bundled-demo URI without probing its own
loopback, because the stream exists only inside the scheduled DockerWorker.
For an external source, it validates the URI and probes it when local
`ffprobe` is available. If the Mac has no `ffprobe`, reachability is deferred
to the scheduled NVIDIA worker, which owns the actual FFmpeg connection and
surfaces an explicit analysis error if the source cannot be opened.

## Run and inspect

From the catalog:

```bash
mn blueprint run cctv_operator --web-ui
```

The launch confirmation reports the stable job-scoped URL. The Web UI skill
writes the dynamically allocated Docker listener as private proxy metadata,
and MirrorNeuron forwards the iframe through the local Web UI server. Keep the wildcard listener
for the host-network DockerWorker; binding it to container loopback prevents
the selected node's proxy upstream from reaching it.

From this folder:

```bash
mn blueprint run . --web-ui
```

This builds the worker image with the deterministic fixture and stream server,
starts the stream on first sampler use, and stops it when the runtime cleans up
the shared worker container. No host FFmpeg, MediaMTX container, helper script,
or external CCTV URL is required. The bundled RTSP endpoint remains private to
the DockerWorker while the job-scoped Web UI proxy exposes only the sanitized
MJPEG and SSE routes. `latest_analyzed_frame.jpg` separately shows the exact
frame sent to the model.

To monitor an approved external source instead:

```bash
mn blueprint run . \
  --set video_source.profile=external \
  --set video_source.uri=rtsp://camera.example/live \
  --web-ui
```

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
configuration, schedule, and latest run through the stable Job response service,
even when no CCTV run is active. A question never starts the stream service.
The job-facing agent is limited to interpreting analysis artifacts and serving
responses through the API-owned response MCP; it does not host sample media,
the sample stream, the dashboard, or workflow helper processes.

## Repository validation

```bash
python3 -m py_compile \
  payloads/services/cctv_web_ui.py \
  payloads/agents/visual_detector/scripts/analyze_video_frame.py
jq empty manifest.json
jq empty config/default.json
```

Use the one-command bundled-demo launch above for runtime validation. A real
camera URL is needed only when `video_source.profile=external`.

See [SPEC.md](SPEC.md) for the complete design contract.

## Blueprint package format

This blueprint uses the canonical blueprint/v1 format in both folders and ZIPs.
`manifest.json` contains identity, semantic release version, and document references.
`workflow.json` owns logical topology and policies; `execution.json` owns workers,
resources, and services; `contracts.json` owns input/output and artifact contracts.
Platform descriptors live in `extensions/`, package requirements in
`dependencies.json` when present, and operator defaults in `config/default.json`.
The SDK reads these documents together and compiles the Core execution artifact.
A ZIP contains the same files as the folder. Local overrides and invocation
configuration are resolved by the SDK before launch.
