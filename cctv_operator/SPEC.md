# CCTV Operator 5.2.1 specification

## Purpose and scope

Provide responsive, reviewable factory/hotel monitoring from one approved live
camera per Job. Publish sampled observations, evidence-linked review actions,
coverage gaps and qualified risk hypotheses. All safety/security decisions stay
with an authorized human. No incident prediction guarantee, autonomous physical
response, identity tracking, injury diagnosis or legal-compliance certification.

## Product policy

Factory rules are group_presence, blocked_route, vehicle_proximity and uncovered_head.
Hotel rules are group_presence, blocked_route, person_on_floor and possible_spill.
site.profile selects these and the default notification goal atomically; a blank/omitted monitoring_goal uses
that goal. An explicit custom/Chat goal replaces it. Omitted rules are unexamined.
Custom profile uses explicit operator direction without built-in facility rules.
site.rule_ids can select unique rules within its profile. Up to twelve normalized
named full-view rectangles guide interpretation only. They never imply privacy
masking or metric calibration. Hotel use is limited to approved common areas.

group_presence means at least two real people visible together in the same selected
frame. It is a low-severity observation independent of hazards, movement or helmet
status. The first matching sample can notify even if the group is already present
at startup; arrival requires reliable sampled before-and-after evidence. One person
across multiple frames is not a group. Possible/unclear views do not notify. Existing
per-rule confidence, absence rearming and cooldown apply through the Cosmos notice
path; this policy does not promise inference or end-to-end latency.

Every site finding follows the bounded contract: rule_id, observed/possible/
not_observed status, confidence in 0..1, visible_evidence (<=800 chars) and unique
1-based selected evidence_frames. Unknown rules, unsupported fields, invalid
frames, duplicate rules or nonfinite scores fail. Observed motion/proximity needs
at least two selected frames; uncovered_head needs not_worn/head_visible=true on
its cited frame. No frame can establish required PPE or policy breach. Deterministic
validation binds provenance but cannot prove semantic correctness.

Each factory/hotel forecast requires selected evidence_frames plus risk,
visible_evidence, qualitative time_horizon, severity and recommended_review.
Preserve prediction_not_observed_event qualification and uncalibrated score basis.
A forecast or possible finding is never a confirmed-event notice. Report the
operator-supplied review owner, otherwise Unassigned. Never invent assignments,
deadlines, action completion, speed, distance or external sensor measurements.

## Capture and admission

There is no default stream URL or live sample. Each new hire requires the
supervisor to supply an approved stream URL through the secure setup field;
launch remains blocked until it is saved. Existing saved source configurations
remain explicit overrides. Hiring does not probe a camera. The native monitor
validates the source before emitting a ready session or admitting sampling.
External streams require no local MP4 or recorded-video publisher. Recorded
playback requires an explicit `bundled_demo` profile, local publisher URI and
an approved MP4 path.

Retain the independent resident CUDA relay, person and caption lanes. Default
relay: 1280-wide full-view MJPEG at8FPS, aspect preserved; fps selection precedes
CUDA scale/download. RF-DETR Small FP16 requests5FPS with existing pinned COCO
weights, two-hit confirmation, two-second sampled absence and gap policy.
Missing/corrupt weights fail without downloads or CPU fallback. A stale frame
cannot advance episodes or establish absence. JPEG resizing and batch writes
cannot hold the person-signal lock.

Default caption sequence:4candidateFPS,1.5s pre-roll,0.5s post-roll,<=8 chronological
frames within896pixels, no upscaling. Initial short person appearances can have
less pre-roll; actual timestamps disclose that span. A complete2s empty-scene
window permits the first scene audit. Subsequent audits require15s without an
offered window; pending steering may request an earlier eligible audit. Scheduled
audits are explicit policy and carry scheduled_scene_review/scene_audit metadata;
they do not fabricate person confirmation. No model call is triggered from a
failed frame or an unconfigured audit gate.

One active caption and one latest pending window; >=5s between admissions and
<=12/minute. Configured ceilings are not achieved throughput promises. Unclaimed
frames older than10s expire with a durable counter; requested commands await fresh
evidence. Revisions cannot regress and preserve audit provenance. Completion is
required before slot release; replay returns the same durable artifact. No lost
completion starts overlapping inference. Core and SDK retain delivery/retry
ownership; this blueprint owns only facility sampling/admission policy.

## Inference, outputs and review

Keep fixed parent graph ingress→sampling→vision→reporting, SDK DockerWorker
placement, NVIDIA/CUDA 49152MB admission and single-node execution. The required
camera/UI auxiliary entrypoint uses the SDK monitored-service block; model-registry
and shared-skill contracts remain unchanged. Cosmos3 Nano
Reasoner1.7 NIM receives selected MP4 frames at4FPS and true capture timestamps;
reasoning/4096token answer allowance/300s request deadline remain. Nemotron text
chat remains separate. Preparation and lifecycle are platform-owned. Malformed,
truncated, unsupported or capacity-failed inference is explicit, never clear-scene
success. Camera source/memory/model failures do not certify absence.
Normally stopped Cosmos responses may omit the closing answer tag or contain one
JSON fence. Accept only a complete JSON object after excluding completed private
reasoning. Reject unfinished reasoning, truncation, malformed JSON and trailing
content; do not salvage a partial object or dispatch another inference for parsing.
The visual prompt declares one complete output contract, including site_findings
and selected-frame references on every forecast. Missing references remain an
analysis error; the parser must not invent them from a different finding.

Evidence batches and selected image hashes precede inference. Reports retain
sample interval, source/demo qualification, frame refs, active instruction,
examined/unexamined rules and a facility review queue. A confirmed profile notice
binds the selected newly observable rule's image/time, score and per-rule cooldown.
Independent hazards do not inherit another rule's suppression. Only confident
not_observed evidence rearms a rule; missing/possible/failed views do not. Current
goal revision must still match at publication. Predictions stay distinct from
observed events. Notice acknowledgement is a human action, distinct from delivery.

Authoritative outputs: cctv_report.json/md, final_artifact.json, events.jsonl,
monitoring_state.json, frame_batches and hashed JPEGs, latest_analyzed_frame,
caption_schedule.json, runtime_memory receipts, context_sources/outputs Markdown
and benchmarks/stages.sqlite3. Preserve legacy report field names while describing
analysis counts as sampled sequences, not unique people or exhaustive incidents.
Default host copy: ~/Downloads/cctv-operator; SDK shared run storage is authoritative.

Retain read-only MJPEG/snapshot Web UI, dynamic Job proxy handle, private authenticated
MCP relay and Core live steering. Credentials remain server-side/redacted; no
browser action endpoint. Bundled demo is an explicitly staged approved MP4, looped
by a service-owned MediaMTX/publisher; worker playback times are not original event
times. External RTSP/RTSPS/RTMP/RTMPS never falls back to a demo or CPU decoder.
Local source files must exist on the submitter; missing files fail explicitly.

## History and persistent state

`mn.blocks.services.cctv_web_ui` retains its existing Docker worker, uploads and
entrypoint. Domain `live_service` hooks own the demo publisher process group,
private MCP/relay listeners, resident monitor, first-frame readiness and UI claim.
The SDK supplies lifecycle supervision, per-cycle health and hashed progress.
Its service UI helper owns execution/run identity, generation and claim status;
the blueprint must not override those reserved metadata fields. Startup health
promotes the claim to running, and cleanup preserves SDK ownership bookkeeping
so stopped/failed updates cannot overwrite a replacement generation.
Listener health/checkpoints run every60s, independently of camera/person/caption
timing. Lane failures keep their existing separate visible health; they neither
certify absence nor automatically kill the other lane. Startup failure closes
already-created resources; stop also closes listeners and preview threads. Core
stop/pause retains progress without successful terminal caching, so resume can
reconstruct resources on the same attached service run. Checkpoint capacity64MiB
requires explicit service replacement/rotation before exhaustion; no automatic
evidence deletion is claimed. Offline tests cover real loopback listeners,
partial startup, health failure, replay and publisher process-group ownership.
The migrated path has not been qualified on a live camera/GPU.

Retain complete authored Markdown Facts/Relations/Notes in camera/source Job scope.
Current selected frames take precedence over historical text. Prior accounts are
navigation, never a before/after image pair or instructions. Membrane hydration
preserves complete records with explicit capacity failures. No raw images, source
credentials or private reasoning enter memory. get_operator_status exposes the
facility queue/coverage and separate lane health. get_video_history returns up to
twelve complete matching accounts across Job runs; time bounds need timezone.
Video Q&A and summaries use the text model, no new image analysis or goal change.
They retain the runtime-prepared text-model binding and generation controls rather
than reapplying catalog model/provider/endpoint defaults. Require structured output,
disable private thinking and retries, and retain the 60-second/1024-token limits
without increasing a smaller runtime allowance.
Preserve citations, capture times, omitted counts and source qualification. No
unique-person/total-appearance claims from repeated samples. Stable Job supervision
and response services remain SDK-owned, including operation receipts and lifecycle.

## Measurement and acceptance

See BENCHMARKS.md for exact boundaries. Add caption.preprocess timing; keep frame
age, person preparation/inference/policy, caption queue/dispatch/model wait/inference,
memory and historical-Q&A measurements separate. Fingerprints include implementation,
model/hardware/configuration/site profile and footage cohort. No pooling across
variants; successful retained percentiles exclude errors/skips, which remain visible.
Timestamps begin at worker JPEG availability, excluding sensor/network/decode before
that boundary. Operator display receipt is measured separately.

Offline tests cover gates/audits, rate limits, stale expiry, lane independence,
frame/rule validation, per-rule notice rearming, immutable evidence, credential
redaction, report/memory projection, history scope, controls and manifest contracts.
Real Spark acceptance requires successful CUDA relay and actual RF-DETR/Cosmos work,
durable reports/history and notice evidence, not merely initializer/transport success.
Before customer claims, use independently labeled representative factory/hotel
footage including hard negatives, occlusion/distance/night, outages and busy scenes.
Measure per-rule precision/recall/misses with counts, false notices/camera-hour,
p50/p95 response and skipped coverage under concurrent load. Agree latency/recall
thresholds per site and get human review of evidence and suggested actions. The
shorter default sequence requires comparison to examples/detail-review.json;
examples/smaller-media.json also requires independent site recall validation;
preprocessing speed alone is not detection accuracy or production readiness.

On 2026-10-18 Spark reboot/reconnection and GB10 CUDA/RF-DETR stage checks succeeded.
The 1280/896 image defaults remain because 960/768 saved little GPU time in this
clip and one person count differed, without labeled ground truth. Smaller media
is an explicit site-validation preset. Full workflow CreateJob was rejected by
Spark Core's older response/MCP contract, before an accepted Job or Cosmos report.
End-to-end latency, semantic accuracy, history and notice acceptance remain open.
See README for measured scope and results. Keep the native declared contract;
do not change/reinstall runtime or weaken validation to bypass this blocker.

## Block composition (5.1.0)

The camera/UI owner uses the SDK monitored-service block. The ingress executor
uses `mn.blocks.event_processing@1` and the direct native monitoring hook.
Complete scoped state replaces mutable agent dictionaries; declared logical
ports preserve the existing start/steering edges. Core retains completion and
delivery. Validation is shared with the submission boundary, while successful
delivery replay reuses its committed result. Unknown commands and rejected
sources cannot commit a ready session. The sampler also uses a native event
hook, with `ready` and `next` ports preserving the existing frame and cadence
edges. Instruction updates freeze the SDK's command `input_key`, timestamp and
revision before requesting an idempotent resident claim. Lost RPC replies fail
the attempt and retry the same physical invocation identity; they cannot silently
consume or release a window. Completed admission and byte capture freeze before
publication, so publication repair cannot claim another window. Batch schema,
identity, counts, chronological finite timestamps, safe paths and every selected
image hash are checked. The manifest is bounded to 1 MiB and total selected
evidence to 32 MiB; shared event/handoff inventory limits also apply.
`frame_evidence` is a scoped committed record containing the original batch
message and captured file references. `monitoring_state.json` and
`sampling_state.json` are accepted-state projections rather than input authority.
The resident resource retains monotonic monitoring intent across delayed views,
JPEG preprocessing and restart. Demo sampling probes the publisher owned by the
resident service; it cannot launch or stop it. Detection and reporting also use
native event hooks and require explicit committed peer-reference identities.
The SDK imports complete private handoff graphs without decoding away those
event-input references. Vision validates the batch, freezes prompts/media and
uses the shared managed-model request with zero transport retries. Raw response
receipts precede domain interpretation and effect receipts; original response
timing survives replay. Missing uncertain outcomes keep admission stalled.
Known invalid replies produce analysis errors rather than clear-scene success.
Per-batch immutable completion receipts are acknowledged through the resident
resource RPC; late retries cannot erase newer completions. Camera source
Markdown derives from immutable prior accepted bytes with the existing 4 MiB
rollover bound. Public latest-frame, memory and report names are declared through
SDK publication and materialized by Core after state acceptance. Report history
retains its existing 500-observation/detection/sampling and 100-error/notice/
delivery bounds. The cumulative report state points to the publication's same
committed bytes, avoiding an additional full report copy in each handoff graph.
Native event workers start with a fresh
run; pre-migration plain-dictionary state is rejected rather than guessed.
Existing CUDA placement, source/model
policy, event edges and auxiliary-service timing stay intact. Require matching
SDK dev27 / blocks dev27 source and Core event/publication support before hook execution.
This is an offline-tested source migration, not a live deployment qualification.
Supervision remains bounded to 1,000,000 health cycles / 64 MiB of checkpoints;
rotate the service before either bound. Camera timing remains independent of
the 60-second health interval.
