# CCTV Operator specification

## Objective

Provide one reviewable, steerable live CCTV workflow without sending
source-frame-rate video to the model.

## Consolidated behavior

The runtime accepts one live stream. Historical file and directory processing
are outside this product contract.

## Source contract

`video_source.mode` is fixed to `stream`. `video_source.uri` must contain one
RTSP, RTSPS, RTMP, or RTMPS URI. Stream credentials are redacted from logs,
events, browser URLs, and public service artifacts. A file URI, unsupported
scheme, unreachable stream, decode failure, or model failure is explicit;
there is no automatic switch to a demo source or CPU decoder.
The submission-side validator always checks mode and URI syntax. It probes
reachability when `ffprobe` is available locally; otherwise it defers that
check to the scheduled NVIDIA worker so a Mac control node does not need media
tooling merely to submit a distributed run.

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

The sampler and detector run in one SDK-managed shared DockerWorker on the
selected NVIDIA node. The sampler owns the exclusive GPU device allocation; the
detector retains NVIDIA/CUDA placement constraints and reuses that GPU-enabled
container, so a single-GPU node is valid. FFmpeg uses CUDA decode and
`scale_cuda` for selected JPEGs. The low-resolution proxy comparison is
deterministic local preprocessing, not a model call. No CPU decoder or Mac-only
execution fallback exists.

Docker Model Runner requests disable model reasoning through the llama.cpp
chat-template control so the bounded token budget is spent on the required
structured visual observation. Empty, reasoning-only, truncated, or malformed
model output is an explicit frame-analysis failure; it is never converted into
a synthetic “no detection” result.

This small FFmpeg CUDA worker is the preferred single-DGX-Spark design. It avoids a large DeepStream service image; DeepStream remains a future option for deployments that need batched multi-camera pipelines, tracker plugins, or high camera density.

The runtime placement mode is `distributed` and scheduling remains
constraint-driven. A cluster containing only Spark is valid: all nodes are
placed there. In a Mac + Spark cluster, the NVIDIA/CUDA constraint keeps the
sampler and detector on Spark while HostLocal report and UI nodes remain
portable. Cross-node batch and report access uses the runtime shared-storage
contract; the blueprint passes run-relative artifact references and contains no
machine address or node-selection logic. The Mac may own the job lease while
the cluster scheduler binpacks every workflow agent on Spark; this is still a
multi-node control/data-plane deployment. Once both runtimes are healthy at
submission, Core reports `multi_node` reliability and enables cluster recovery.

## Web UI deployment decision

The manifest declares a blueprint-owned HostLocal `cctv_web_ui` service. Its
specific UI spec, `/actions/steer-monitoring` handler, payload validation,
state projection, and Core call live in `payloads/services/cctv_web_ui.py`.
The generic `mirrorneuron-web-ui-skill` hosts and renders the validated spec
with `vercel-labs/json-render`; it knows no CCTV routes or policy.
The rendered dashboard displays the current watch target and provides a
bounded 500-character prompt form that updates the declared
`steer_monitoring` live input.
The adaptive sampler durably writes the current run-scoped instruction to
`monitoring_state.json`. The Web UI uses that artifact as the authoritative
watch-target state. It projects operational status and review history from
`cctv_report.json` and `latest_analyzed_frame.json`, treating event records as
supplemental activity history. This keeps the UI meaningful when HostLocal
services are scheduled on a different cluster node from the detector.

The HostLocal service never opens the RTSP source and never launches FFmpeg.
The optional `web_ui.preview.url` setting must name an absolute,
credential-free HTTP(S) media URL supplied by an external camera gateway. HLS
playlists are rendered by the generic web UI skill. A missing preview leaves a
blank media surface and never stops sampling. The local `scripts/sample_rtsp.sh`
development helper publishes the fixture over RTSP and uses MediaMTX itself as
the HLS proxy; that sample proxy is not a Core responsibility. The UI
separately renders `latest_analyzed_frame.jpg` so the operator can distinguish
the smooth preview from model evidence. There is no Gradio path and no
`mn-api` live-input REST route. The operator-facing `web_ui.service.port`
setting is projected into the HostLocal port reservation and service health
declaration as one runtime contract. `web_ui.service.host` is projected into
the declared service address. The CLI `--web-ui-host` and `--web-ui-port`
options override those settings for one run. The default wildcard listener is
required for container port publication and exposes the service to peers that
can reach the published port; the service does not add authentication.

## Persistent job data

Knowledge, RAG, and durable application state are isolated by stable `job_id`
and survive multiple runs. Run media inputs and review outputs remain
run-scoped. This blueprint has no bundle seed for runtime-generated CCTV
knowledge and never clears job data during run cleanup.

The stable job exposes the API-owned read-only supervisory MCP while `mn-api`
is reachable. It reports bounded role, configuration, lifecycle, schedule, and
latest-run context without launching the stream workflow or exposing camera
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
