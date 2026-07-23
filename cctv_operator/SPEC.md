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

## Runtime graph and live input

The logical processing path is `ingress → adaptive_frame_sampler →
visual_detector → report_writer`. The sampler self-schedules at the configured
proxy cadence; there is no runtime timer or video-specific Core module. The
generic live-video skill owns a run-scoped persistent FFmpeg connection, proxy
comparison primitives, selection, batch persistence, and preview relay
mechanics. The blueprint sampler owns CCTV cadence, event names, steering
priority, and product metadata; the detector owns prompt, observation, alert,
and report semantics.

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

This small FFmpeg CUDA worker is the preferred single-DGX-Spark design. It avoids a large DeepStream service image; DeepStream remains a future option for deployments that need batched multi-camera pipelines, tracker plugins, or high camera density.

## Web UI deployment decision

The manifest declares a blueprint-owned HostLocal `cctv_web_ui` service. Its
specific UI spec, `/actions/steer-monitoring` handler, payload validation,
state projection, and Core call live in `payloads/services/cctv_web_ui.py`.
The generic `mirrorneuron-web-ui-skill` hosts and renders the validated spec
with `vercel-labs/json-render`; it knows no CCTV routes or policy.

The service uses the optional relay from
`mirrorneuron-live-video-analysis-skill` to expose a credential-free HLS path.
Relay failure is visible but never stops sampling. The UI separately renders
`latest_analyzed_frame.jpg` so the operator can distinguish the smooth preview
from model evidence. There is no Gradio path and no `mn-api` live-input REST
route.

## Persistent job data

Knowledge, RAG, and durable application state are isolated by stable `job_id`
and survive multiple runs. Run media inputs and review outputs remain
run-scoped. This blueprint has no bundle seed for runtime-generated CCTV
knowledge and never clears job data during run cleanup.

## Outputs and review boundary

Every report preserves source name, stream observation time, detections,
confidence, alert records, errors, sampling trigger, instruction revision, and
batch reference. The durable outputs are:

- `events.jsonl`
- `cctv_report.json`
- `cctv_report.md`
- `final_artifact.json`
- `web_ui.json`
- `frame_batches/<batch_id>/batch.json`
- selected batch JPEGs
- `latest_analyzed_frame.jpg`
- `latest_analyzed_frame.json`

Evaluation should measure decode reliability, frame-to-observation latency, detection precision/recall, false alerts, missed detections, cooldown correctness, source provenance, and reviewer usefulness. This is decision support, not a certified safety or security system. Human review, privacy/retention policy, camera authorization, incident-response integration, and validation on representative footage remain deployment responsibilities.
