# CCTV Operator specification

## Objective

Provide one reviewable, steerable live CCTV workflow without sending
source-frame-rate video to the model.

## Consolidated behavior

The runtime accepts one live stream. Historical file and directory processing
are outside this product contract.

## Source contract

`video_source.mode` is fixed to `stream`. The default
`video_source.profile=bundled_demo` uses the fixed
`rtsp://127.0.0.1:8554/cctv-demo` URI. The shared NVIDIA DockerWorker contains
the deterministic sample video, a pinned MediaMTX server, and the FFmpeg
publisher, and starts them before the sampler opens the stream. This is an
explicit source profile, not an error fallback.

`video_source.profile=external` requires one RTSP, RTSPS, RTMP, or RTMPS URI.
Stream credentials are redacted from logs, events, browser URLs, and public
service artifacts. A file URI, unsupported scheme, unreachable stream, decode
failure, or model failure is explicit; an external source never falls back to
the bundled demo or a CPU decoder. The submission-side validator always checks
the profile, mode, and URI syntax. It does not probe the submit host's loopback
for the bundled source, which exists only in the worker. It probes an external
source when `ffprobe` is available locally; otherwise it defers that check to
the scheduled NVIDIA worker so a Mac control node does not need media tooling
merely to submit a single-node run owned by the qualifying NVIDIA runtime.

## Runtime graph and live input

The logical processing path is `ingress → adaptive_frame_sampler →
visual_detector → report_writer`. The sampler self-schedules at the configured
proxy cadence; there is no runtime timer or video-specific Core module. The
generic live-video skill owns a run-scoped persistent FFmpeg connection, proxy
comparison primitives, selection, and batch persistence. The blueprint sampler
owns CCTV cadence, event names, steering priority, and product metadata; the
detector owns prompt, observation, alert, and report semantics. The configured
`inputs.payload.visual_targets` are rendered into every detector prompt. The
blueprint-owned detection policy matches observations against
`alert_policy.notify_on`, then applies `min_confidence` and
`cooldown_seconds`. The default `human_notice_only` mode creates a reviewable
human notice without attempting an external delivery.

The manifest declares `contracts.live_inputs.steer_monitoring`. Core resolves
that identifier to `ingress` and `cctv_operator_steer`; callers cannot name a
physical agent or stream. The payload accepts `instruction` (500 characters
maximum), `clear`, and `analyze_now`. Core assigns the command ID from the
required idempotency key and preserves it in live-input metadata.

Steering state is stored in the adaptive sampler’s agent state with a monotonically increasing revision and never crosses run boundaries.

## Adaptive sampling contract

- Proxy inspection: 1 FPS at 320 pixels.
- Baseline model analysis: every 20 seconds.
- Scene trigger: normalized grayscale mean absolute difference of at least `0.18` for two consecutive proxy samples.
- Event window: up to three seconds of in-memory pre-roll plus five seconds of post-trigger capture.
- Candidate cadence: 5 FPS.
- Selection: at most ten unique frames, preserving the first and last frames and filling remaining slots by change score and temporal distance.
- Backpressure: one active model request, one pending batch, and six calls per minute. Priority is on-demand, scene event, then baseline. Dropped or coalesced work emits `cctv_operator_sample_skipped`.

Every selected batch is durably written before its reference is emitted. Messages contain only bounded coordination fields and artifact references.

Significant detections can emit `human_notice` and optional alert-delivery
events. The workflow never performs physical security actions.

## NVIDIA requirement and media path

The manifest hard-requires `nvidia`, `cuda`, one NVIDIA GPU, and 49,152 MB or more of GPU/unified IGP memory. `mn-python-sdk` owns cluster resource validation, including DGX Spark unified-memory accounting. The blueprint only declares the requirement and does not implement another hardware probe.

Every executable CCTV node runs in an SDK-managed DockerWorker on the selected
NVIDIA node. The sampler owns the exclusive GPU device allocation; ingress,
detector, and report writer reuse that GPU-enabled container, so a single-GPU
node is valid. The Web UI uses that same host-network DockerWorker and shared
runtime artifact volume, avoiding both another GPU reservation and another
transfer of the bundled sample-video build payload. FFmpeg uses CUDA decode and
`scale_cuda` for selected JPEGs. The low-resolution proxy comparison is
deterministic local preprocessing, not a model call. No CPU decoder or Mac-only
execution fallback exists.

In bundled-demo mode, the same Docker image also owns test-stream generation.
Its pinned MediaMTX binary and bundled MP4 are build-context assets, and an
idempotent startup script maintains the looping publisher for the life of the
shared container. Demo publishing may encode the fixture with `libx264`; this
does not alter the NVIDIA/CUDA-only decoding and frame-preparation contract of
the sampler. Worker cleanup terminates the server and publisher with the
container, so there is no separate host process or test-stream container to
start and stop.

Docker Model Runner requests disable model reasoning through the llama.cpp
chat-template control so the bounded token budget is spent on the required
structured visual observation. Empty, reasoning-only, truncated, or malformed
model output is an explicit frame-analysis failure; it is never converted into
a synthetic “no detection” result.

The model contract is the explicit cataloged `nemotron3:q4_K_M` Docker Model
Runner artifact. It is a blueprint-specific multimodal model, not the cluster
`default` route. Its first use lazily installs the exact short Docker Model
Runner artifact on the selected qualifying NVIDIA node, registers it, and
refreshes the node-local LiteLLM gateway. The detector uses that LiteLLM route;
it never sends model traffic directly to a Docker Model Runner endpoint or to
the submit host. The blueprint never falls back to the text-only
`nemotron-3.5-lightning:latest` route.

This small FFmpeg CUDA worker is the preferred single-DGX-Spark design. It avoids a large DeepStream service image; DeepStream remains a future option for deployments that need batched multi-camera pipelines, tracker plugins, or high camera density.

The runtime placement mode is `single_node` and selection remains
constraint-driven. A cluster containing only Spark is valid. In a Mac + Spark
federation, the NVIDIA/CUDA and 49,152 MB requirements make Spark the only
eligible job owner. The SDK forwards the job definition to Spark's Core and
pins every workflow and control node there, so a workflow never crosses the
distinct coordination-store boundary between federated runtimes. The
blueprint contains no machine address or hard-coded node name; the Mac remains
the submitting control plane and observes the Spark-owned job through the
federation projection.

## Web UI deployment decision

The manifest declares a blueprint-owned DockerWorker `cctv_web_ui` service in
the same shared host-network container as the stream and analysis workers. Its
HTML page, MJPEG relay, SSE event feed, and state projection live in
`payloads/services/cctv_web_ui.py`. The
generic `mirrorneuron-web-ui-skill` claims the already-bound endpoint and its
proxy allowlist; it knows no CCTV routes or policy. The dashboard is read-only,
displays the current watch target, and leaves updates to an external chat AI
calling the blueprint MCP and its declared `steer_monitoring` live input.
The adaptive sampler durably writes the current run-scoped instruction to
`monitoring_state.json`. The Web UI uses that artifact as the authoritative
watch-target state. It projects operational status and review history from
`cctv_report.json` and `latest_analyzed_frame.json`, treating event records as
supplemental activity history. This keeps the UI meaningful without depending
on transient relay files.

The Web UI process opens the configured RTSP/RTMP source once and fans a
multipart MJPEG stream out to all connected browser clients. Its FFmpeg process
requires CUDA decode and `scale_cuda`; it does not silently fall back to CPU
decode. NVIDIA FFmpeg has no MJPEG NVENC codec, so the final JPEG entropy encode
uses FFmpeg's MJPEG encoder after GPU download. The source URI and credentials
never appear in the browser route or public service metadata. The operator
event projection is delivered over server-sent events, sorted newest first, and
the browser returns the feed to the top when a new event arrives. The UI
separately renders `latest_analyzed_frame.jpg` as model evidence. There is no
Gradio path, browser steering action, or `mn-api` live-input REST route.
`web_ui.service.port` defaults to `0`; the
generic Web UI skill resolves a runtime-reserved port or allows an
operating-system-selected free port. The service claims that actual port in the
skill-owned `mn.web_ui.proxy.v1` handle. There is no
blueprint port range, fixed reservation, or host-side registrar. The operator
receives only the local `/jobs/<job_id>/ui` route; the worker address and
dynamic port remain iframe-proxy upstream data. The wildcard listener is
required for the host-network DockerWorker.

## Persistent job data

Knowledge, RAG, and durable application state are isolated by stable `job_id`
and survive multiple runs. Run media inputs and review outputs remain
run-scoped. This blueprint has no bundle seed for runtime-generated CCTV
knowledge and never clears job data during run cleanup.

The stable job exposes the API-owned top-level Job response service while `mn-api`
is reachable. Its job-facing agent is limited to interpreting the analysis
artifacts and responding through the response MCP. It reports bounded role,
configuration, lifecycle, schedule, and latest-run context without hosting the
sample data, stream, Web UI, or helper processes and without exposing camera
credentials, raw logs, host paths, or unrestricted artifacts.

## Outputs and review boundary

Every report preserves source name, stream observation time, detections,
confidence, alert records, errors, sampling trigger, instruction revision, and
batch reference. The durable outputs are:

- `events.jsonl`
- `monitoring_state.json`
- `cctv_report.json`
- `cctv_report.md`
- `final_artifact.json`
- `web_ui.json`
- `frame_batches/<batch_id>/batch.json`
- selected batch JPEGs
- `latest_analyzed_frame.jpg`
- `latest_analyzed_frame.json`

Evaluation should measure decode reliability, frame-to-observation latency, detection precision/recall, false alerts, missed detections, cooldown correctness, source provenance, and reviewer usefulness. This is decision support, not a certified safety or security system. Human review, privacy/retention policy, camera authorization, incident-response integration, and validation on representative footage remain deployment responsibilities.
