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
a pinned MediaMTX server and the FFmpeg publisher. The SDK stages
`video_source.demo_file` from `/Volumes/128GB/videos/nv-warehouse-4cams/Camera.mp4`
on the submitter into shared Job inputs before launch; no other videos are
staged. The file must exist, be nonempty and fit the 512 MiB input limit.
External profile skips demo staging. Playback is looped recorded footage, not
live surveillance evidence. Capture times are worker playback times, not
original recording dates. The long-running Web UI service starts the publisher
in its own process group. Sampling ticks wait for stream readiness without
owning the publisher; tick cleanup must not interrupt playback. Runtime
cancellation terminates the publisher with the service. This is an
explicit source profile, not an error fallback.

`video_source.profile=external` requires one RTSP, RTSPS, RTMP, or RTMPS URI.
When submitted from a Mac, an external loopback or wildcard URI is invalid:
the NVIDIA worker runs on a different node and cannot reach a stream bound only
to the Mac's loopback address. The stream server must listen on a network
interface and the configured URI must resolve to an address reachable from the
selected NVIDIA node. A stream local to that NVIDIA node may use loopback when
submitted from that node.
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

Conversation monitoring controls use the authenticated HostLocal MCP sidecar
over host-network loopback to submit Core live inputs. The Docker video worker
holds only a run-scoped control credential and does not receive a Core gRPC
client identity.

The Core caption path retains the entrypoints `ingress → adaptive_frame_sampler
→ visual_detector → report_writer`. Its sampler self-schedules caption claims
and applies steering; there is no video-specific Core module. The resident
Web UI service owns one persistent CUDA FFmpeg relay and two independent lanes:
RF-DETR person events and periodic caption-window capture. Person inference
does not depend on Core tick delivery or Cosmos. The generic live-video skill
owns diverse-frame selection and durable batch persistence. The blueprint owns
caption cadence, bounded admission, event policy, steering and product metadata;
the caption handler owns prompts, observations, memory and complex-goal notices. The configured
`inputs.payload.visual_targets` are rendered into every detector prompt. The
blueprint-owned caption detection policy matches observations against
`alert_policy.notify_on`, or the active chat-set visual goal when present, then applies `min_confidence` and
`cooldown_seconds`. The default `human_notice_only` mode creates a reviewable
human notice without attempting an external delivery.

The manifest declares `contracts.live_inputs.steer_monitoring`. Core resolves
that identifier to `ingress` and `cctv_operator_steer`; callers cannot name a
physical agent or stream. The payload accepts `instruction` (500 characters
maximum), `clear`, `analyze_now`, and an optional bounded `command_id`.
The conversation tool supplies the same command ID in the payload and idempotency
key. The sampler preserves the explicit ID, using runtime metadata for callers
that omit it. The active instruction becomes the vision prompt's primary goal;
clearing it restores the default targets. Readiness to accept a goal is independent
of whether the first frame has already been analyzed.

The response tool descriptions distinguish monitoring actions from activity
queries and specify valid cursor and boolean-string arguments. Polite requests
such as “can you focus on find foreign object on the floor?” are actions. The
active instruction replaces the default target list in the actual vision prompt;
stationary floor objects remain eligible evidence for that goal. Clearing the
instruction restores the saved monitoring goal. Command completion confirms the sampler
applied the instruction, not that a new model observation has already completed.

The saved `inputs.payload.monitoring_goal` defaults to
`A person is visible in the video.` Resident RF-DETR confirms sampled person
presence and publishes direct notices. Cosmos independently describes observable
activity and writes that account to authored Markdown context memory. One visible person meets the
goal; a group is not required. Shadows, reflections, signage and speech alone
do not qualify. Conversation questions read saved Markdown history through the
text model, without further image interpretation. A corridor obstruction
request remains a sufficiently specific goal; a single frame cannot certify
safe passage.
The command status separately exposes `analysis_ready` and the first finding at
the applied instruction revision. The sampler restores the latest durable
instruction if a later agent-state snapshot is stale.

Steering state is stored in the adaptive sampler’s agent state with a monotonically increasing revision and never crosses run boundaries.

## Resident pipeline contract

- One CUDA camera relay feeds separate resident person-detection and caption-sampling threads.
- RF-DETR Small, PyTorch FP16, requests 5 FPS; Medium is a prepared comparison alternative. The published package and checkpoint hashes are pinned. Runtime downloads and CPU fallback are prohibited.
- Person presence requires two consecutive detections at confidence 0.55. Two seconds of sampled absence rearm the scene episode. A gap greater than two seconds resets persistence without proving exit or identity. Instruction revisions rearm evaluation.
- Canonical simple person-presence goals use RF-DETR notices directly. Arbitrary person activity, zones and complex conditions use Cosmos reasoning; no substring classifier may treat “a person falling” as mere presence.
- Caption admission has an independent ten-second baseline, even for empty scenes. A separate 4 FPS sampler retains a rolling four-second window, selects at most twelve unique chronological frames and persists each batch before Core delivery.
- One caption is in flight and one latest window is pending, with six admissions/minute. Replaced windows are counted; requested goals retain their command/revision. Durable completion releases admission on success or error. Lost completion is exposed as stalled and must not cause overlapping model work.
- Caption or memory latency cannot block person notices. Detector failure does not close caption sampling; each lane exposes its own health. No failure is an absent-person observation.
- Cosmos captions person activity but cannot duplicate RF-DETR presence notices. A superseded complex-goal revision can enter history but cannot publish a notice under the new goal.

Only goal matches passing confidence and cooldown create `human_notice` and
optional configured Slack delivery. Person evidence is durable before the SDK
human notice and MCP activity are published. Complex-goal evidence uses the
validated model-selected frame index. Quiet and unrelated captions stay in
history without notifying. Notices retain observation time, recording
qualification and bounded immutable evidence. The workflow performs no physical
security actions.

`answer_video_question` and `get_video_summary` read complete authored Markdown
observations in context memory and answer with the configured primary text
model. Cosmos understands independently sampled image sequences and create
that Markdown history; history questions never retrieve frames or invoke Cosmos.
Both are asynchronous read operations: a UUID receipt returns immediately,
`get_video_answer` reports the result, and the Job response service updates the
original turn. One request is pending at a time; the completion timeout is 90
seconds and the text-model call is bounded to 60 seconds without retries.
Capture-time bounds require a timezone. The twelve most recent matching complete
accounts are admitted within the configured context-memory byte limit; omissions
and insufficient capacity are explicit. Returned citation aliases must resolve
to the hydrated Markdown revisions. Summary and question reads are current-run
scoped; `get_video_history` spans runs for the same camera and source. Questions
never change monitoring. Preserve forecasts, recording qualifications and
sampling gaps. Missing history does not mean zero people. Do not sum repeated
observation counts to claim unique people or cumulative appearances.

`human_notice` is the reviewable conversation event for video-analysis findings.
A single event's SDK MCP activity may carry an inline JPEG of at most 75 KiB;
activity history omits image bytes. Transport receipt does not mark a notice
reviewed. The desktop reconciles MCP delivery and the runtime notice by notice
and run identity. A pending
`human_input_requested` event is exposed by the API-owned
Job MCP as a protocol `2026-07-28` Multi Round-Trip Request: the client answers
the elicitation and the suspended Job request resumes. MRTR is not used as an
unsolicited push channel.

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
Its pinned MediaMTX binary is a build-context asset; the MP4 is a staged Job input. An
idempotent startup script maintains the looping publisher for the life of the
shared container. Demo publishing may encode the fixture with `libx264`; this
does not alter the NVIDIA/CUDA-only decoding and frame-preparation contract of
the sampler. Worker cleanup terminates the server and publisher with the
container, so there is no separate host process or test-stream container to
start and stop.

The vision model is the blueprint-owned `cosmos3-nano-reasoner:1.7` Docker/NVIDIA NIM
backend (`source: docker`), served through the selected node's managed LiteLLM
route. Its full `model_spec` is declared in `execution.json` and transferred
through the SDK custom-model contract. Catalog absence and compatibility
findings warn without blocking installation; malformed definitions and actual
installation failures remain errors. The runtime owns install/start/stop/unload; the blueprint does not run NIM
installation commands. First installation requires `NGC_API_KEY` (or
`NGC_CLI_API_KEY`) in the owning runtime's environment. Keep it out of blueprint
config and chat. The existing `nemotron-3.5-lightning:latest` DMR model remains
the text chat model and is reused when installed. Cosmos uses temporal
`video_url` containing an MP4 of the selected chronological JPEGs at 4 FPS,
reasoning and a 4,096-token output budget; private reasoning is
excluded from memory. Missing, malformed or truncated final answers are explicit
analysis failures, never fabricated clear-scene observations.

This FFmpeg CUDA worker is the preferred single-DGX-Spark design. It avoids a large DeepStream service image; DeepStream remains a future option for deployments that need batched multi-camera pipelines, tracker plugins, or high camera density.

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
MJPEG relay and SSE transport live in `payloads/services/cctv_web_ui.py`;
`payloads/domain/media.py` owns the media page and `payloads/domain/dashboard.py`
owns the observation projection. The
generic `mn-python-sdk-web-ui` claims the already-bound endpoint and its
proxy allowlist; it knows no CCTV routes or policy. The page is read-only and
shows only live video and the latest analyzed snapshot, leaving updates to chat
calling the blueprint MCP and its declared `steer_monitoring` live input.
The adaptive sampler durably writes the current run-scoped instruction to
`monitoring_state.json`. The service uses that artifact as the authoritative
watch-target state. It projects operational status and review history from
`cctv_report.json` and `latest_analyzed_frame.json`, treating event records as
supplemental activity history. Conversation observations therefore do not depend
on transient relay files.

The Web UI process opens the configured RTSP/RTMP source once and fans a
multipart MJPEG stream out to all connected browser clients. Its FFmpeg process
requires CUDA decode and `scale_cuda`; it does not silently fall back to CPU
decode. NVIDIA FFmpeg has no MJPEG NVENC codec, so the final JPEG entropy encode
uses FFmpeg's MJPEG encoder after GPU download. The source URI and credentials
never appear in the browser route or public service metadata. The operator
event projection is delivered over server-sent events to refresh media. The browser
does not render event text or telemetry. Conversation events carry optional
bounded display details derived from that individual observation, including
confidence, risk, analyzed frame count, and model latency when present. The UI
renders `latest_analyzed_frame.jpg` as model evidence. There is no
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

The SDK MRTR listener is loopback-only. Because the Core-container sidecar has
a separate network namespace, a blueprint relay forwards only MCP and health
requests and requires a random per-run token. The private endpoint artifact is
owner-readable/writable only. The relay strips its credential before forwarding
to the loopback MCP server; it is never part of public UI metadata.

Knowledge, RAG, and durable application state are isolated by stable `job_id`
and survive multiple runs. Run media inputs and review outputs remain
run-scoped. The root `knowledge/` folder seeds reference guidance and clearly labeled
synthetic CCTV examples through the shared runtime convention; these are never
live findings. Run cleanup never clears job data.

The stable job exposes the API-owned top-level Job response service while `mn-api`
is reachable. During an active run, the CCTV DockerWorker hosts the private SDK
MRTR server that owns the run-scoped `cctv-operator-mcp` tools and reads the
same durable run artifacts as the Web UI. A dependency-free HostLocal sidecar
only proxies that listener onto the guarded scheduler port, so the host-network
video worker does not compete with the runtime port broker and the sidecar does
not require a prepared Python environment. The MCP agent owns the bounded
status, activity watch, monitoring-instruction, and notice-acknowledgement tools;
the Job response agent resolves exactly one passing service for the active run.
It uses `watch_operator_activity` to receive the same sanitized event projection
shown in the Web UI through protocol `2026-07-28` MRTR, then relays that activity
through the chat-facing Job MCP. An MRTR delivery receipt is transport-only and
must not acknowledge a durable operator notice. The response path never exposes
camera credentials, raw logs, host paths, unrestricted artifacts, or the private
MCP endpoint to the desktop renderer.

## Outputs and review boundary

Version 1.3.1 sets the default host output folder to
`~/Downloads/cctv-operator`, matching the declared job name. Previously
submitted jobs retain their configured destination.

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

OtterDesk initial setup offers an explicit sample start with all bundled defaults.
Personal-stream setup requires a secure stream URL; the sampling, target, notice,
and output defaults remain optional to edit. Appearance is not a launch requirement.

The host MCP sidecar requests an automatic scheduler port. Its listener, service
registration, and health check use that same allocation; no run binds a fixed
MCP port. A missing allocation fails before the sidecar starts.

## Context engine contract

The authored Markdown foundation from version 1.4.1 publishes camera observations as authored Markdown Facts, Relations
and complete sampled-account detail. Membrane is the Context Intelligent System;
runtime memory is its history component. Native DuckDB selects the recent three
by the actual observation timestamp, then verifies and hydrates each complete
qualified record. The schema declaration has its own persisted publication clock
and never counts as a sampled observation. Job scope preserves history across
runs. Missing observation timestamps fail explicitly; they are never invented.
Deploy the matching shared SDK and Membrane SDK with this blueprint. Existing
legacy JSON observations require reviewed republication to adopt the new format.

The `mn.context` descriptor enables Membrane runtime memory and declares `mirrorneuron-python-sdk[context]`. The detector queries the most recent three sampled observations for the same camera and source before candidate verification, then stores the new observation after analysis. Observations are job-scoped so history survives runs; each retains its run, timestamp, instruction revision, confidence, qualification and durable frame-batch reference. Camera credentials, source URLs, image bytes and external RAG passages are excluded from text memory. Historical screening-only records retain an unknown detection count. Historical text never establishes continuous coverage, identity, intent or an unobserved first appearance. The Markdown/DuckDB service runs on CPU; the configured vision route and CUDA media path retain their contracts. Query receipts and source handles stay in `runtime_memory/` sidecars; only whole bounded results reach the model. Missing history and insufficient capacity are explicit. Set `text_memory.enabled=false` to disable the consumer.

## Sampled understanding and risk memory

Every scheduled caption sequence is analyzed, including quiet scenes and batches
with no configured-target match. A condition check or approval does not block the
scene account. Cosmos records observed activity separately from `risk_predictions`.
Each prediction includes visible evidence, a qualitative time horizon, confidence,
severity and recommended human review. Predictions are hypotheses, not observed
incidents or a guarantee of safety. Consequential actions remain human decisions.

The detector reads three complete previous Markdown accounts for the same camera
and source, then publishes its new typed Facts/Relations/account through Membrane.
Capture start/end times, instruction revision, batch reference and uncertainty
survive across runs in Job-scoped memory. No raw images, source credentials or
private model reasoning enter that memory. Default admission is 49,152 bytes;
insufficient capacity is explicit and complete records are never silently cut.

Chat uses `get_operator_status` for current understanding and predicted risks,
and `get_video_history` for up to twelve complete historical accounts, optionally
bounded by timezone-qualified `after` and `before` times. Use an earlier `before`
for another page. Answers retain times and evidence references and disclose the
bounded result. Prepared hourly Markdown (split into additional files at 4 MiB) under Job output
`context_sources/outputs/` supports cited answers when the monitor is stopped.
Runtime receipts stay in `runtime_memory/`. The prepared source connection has
explicit SDK inventory/corpus limits (512 files, 4 MiB per file, 32 MiB total);
a capacity error must be reported rather than claiming exhaustive history.

The design follows Spark VSS's short-sequence temporal analysis, while composing
it with MirrorNeuron's existing sampler, memory and chat rather than deploying
VSS's complete service stack. See the [NVIDIA Cosmos API](https://docs.nvidia.com/nim/vision-language-models/1.7.0/examples/cosmos-reason3/api.html).

A continuing person episode is reported once and rearms only after sustained sampled absence. Complex goals rearm after confident Cosmos absence. Instruction revisions rearm evaluation while cooldown limits repeated notices.

## Benchmark contract

`benchmarks/stages.sqlite3` retains at most 10,000 measurements by default
(operator bounds: 100–100,000). `get_pipeline_benchmarks` exposes stage labels,
p50/p95/max, cold/warm samples, errors and skipped frames/windows. Distinct
hardware, model/checkpoint, configuration, footage and experiment cohorts are
never pooled. Percentiles describe retained successful measurements; failure
and skip counts remain separate. They do not measure recall or continuous
coverage.

Stage labels explicitly include “RF-DETR for person events”, “Cosmos video
captioning”, “MN caption memory publication” and historical Q&A. Admission wait,
Core dispatch wait and Cosmos-slot wait are separate from inference. Person
frame-to-notice ends after SDK human notice/MCP publication; caption latency ends
after successful enabled MN memory publication. Neither includes desktop
notification receipt. Worker frame-availability timestamps are qualified and
must not be represented as sensor or original recording timestamps.

The opt-in replay harness compares prepared Small/Medium adapters against one
approved labeled JPEG dataset, preserving footage SHA-256, threshold, warmup,
hardware and episode policy. It reports frame-presence precision/recall,
missed/false scene episodes and sampled confirmation delay separately from
GPU/model time. No live cameras, downloads or GPU requests occur in default
tests. See [BENCHMARKS.md](BENCHMARKS.md). Alternative detector adapters must
satisfy the same `load`/`detect` interface and measurement contract before their
results can be compared. No unimplemented detector is claimed as supported.

Version 2.0.1 uses the shared live-video skill's explicit MP4 transport for
LiteLLM chat requests. The proxy can validate and forward `video_url` to NIM;
its standard chat validation rejects NVIDIA's `video_frames` extension. Actual
capture times and gaps remain in the prompt and memory. Only selected frames are
encoded, with one thread and a ten-second bound. Camera decoding stays on CUDA;
encoding does not create another inference request. The video skill minimum is
`1.3.58.dev23`. Existing native pre-decoded support in the skill remains available.
