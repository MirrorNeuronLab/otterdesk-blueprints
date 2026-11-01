# CCTV Operator 5.4.0 specification

## Purpose and scope

Provide responsive, reviewable factory/hotel monitoring from one approved live
camera per Job. Publish sampled observations, evidence-linked review actions,
coverage gaps and qualified risk hypotheses. All safety/security decisions stay
with an authorized human. No incident prediction guarantee, autonomous physical
response, identity tracking, injury diagnosis or legal-compliance certification.

Edge frame evidence uses repetition_penalty=1.1 with the existing output budget
and complete-response checks. A received incomplete answer fails that sample
without repair inference. Current analysis status recovers only after a newer
successful analysis; historical errors remain inspectable in the report/events.
The displayed watch target must use the same configured/profile goal as scene
analysis, with the active run's steering instruction taking precedence.
Caption claim and completion workers must serialize their resident control RPCs
with a bounded local-owner process lock, respecting the adapter's single slot.
They must not hold this control lock during inference or retry received results.

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

Conversation setup must identify the mission, one secure next input, expected
startup checks and where to inspect progress. Use the label Video stream URL,
with the question/help in descriptive text. Never echo its value. Setup fields
require facility-profile confirmation and a secure stream URL before
launch; saving the URL alone is insufficient. Ask the profile first so its rules
are confirmed before connecting. Secondary settings retain their defaults.
The declared setup prompt must resolve from the bundle; the installed manual
must describe readiness and recovery in readable prose rather than serialized
artifact lists.
Domain status and operation summaries distinguish no analysis, current camera
health, queued goal changes, applied goals and analyzed goals. Each missing or
failed result gives a practical next action without invented progress, findings,
ETAs or automatic follow-up promises. History summaries use short Markdown and
retain capture times, citations and qualifications. Generic desktop preparation
indicators, delivery and response protocol remain platform-owned.

A request to focus on whether an observable condition holds is a future Cosmos
prompt change, including a question about whether a person wears a safety helmet.
Translate the subject and condition without reversing negation or demanding site
policy or a currently visible head. Missing visual evidence makes a later result
uncertain; it does not prevent setting the prompt. Clarify only an unspecified
subject or condition. Retrospective questions remain history reads. Confirm the
applied instruction revision separately from its next analyzed frame.

The control sidecar must launch Python directly so SDK submission preparation
recognizes it as a Python HostLocal worker and installs the declared dependencies
in its managed environment. Its run-input client must not depend on packages
incidentally installed in Core's base interpreter.
Live input commands address the public execution ID in MN_RUN_ID. The private
endpoint and output directory use MN_WORKFLOW_RUN_ID. These identities must
remain distinct after resume; a missing execution identity rejects steering.

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

Default caption sequence:4candidateFPS,1.5s pre-roll,0.5s post-roll,<=2 chronological
frames within896pixels, no upscaling. Initial short person appearances can have
less pre-roll; actual timestamps disclose that span. A complete2s empty-scene
window permits the first scene audit. Subsequent audits require15s without an
offered window; pending steering may request an earlier eligible audit. Scheduled
audits are explicit policy and carry scheduled_scene_review/scene_audit metadata;
they do not fabricate person confirmation. No model call is triggered from a
failed frame or an unconfigured audit gate.

A newly confirmed person episode schedules its post-roll even if a scene audit
or previous episode just offered a window. Continuing presence retains the normal
baseline cadence. Claiming still enforces the existing single active request,
minimum interval and per-minute budget; no concurrent Cosmos request is added.

One active caption and one latest pending window; >=5s between admissions and
<=12 Cosmos image requests/minute. Configured ceilings are not achieved throughput promises. Unclaimed
frames older than10s expire with a durable counter; requested commands await fresh
evidence. Revisions cannot regress and preserve audit provenance. Completion is
required before slot release; replay returns the same durable artifact. No lost
completion starts overlapping inference. Core and SDK retain delivery/retry
ownership; this blueprint owns only facility sampling/admission policy.

## Inference, outputs and review

Keep fixed parent graph ingress→sampling→vision→reporting, SDK DockerWorker
placement, NVIDIA/CUDA 49152MB admission and single-node execution. The required
camera/UI auxiliary entrypoint uses the SDK monitored-service block; model-registry
and shared-skill contracts remain unchanged. Cosmos3-Edge 4B uses the managed
Docker/vLLM backend with the official `vllm/vllm-openai:cosmos3` image pinned by
digest, and revision-pinned Hugging Face checkpoint in BF16. The SDK validates
literal server arguments before effects. The recipe explicitly selects XGrammar
structured decoding after the native reasoning phase, a Qwen3-compatible reasoning
parser, optional whitespace disabled,32K context, one sequence
and25% memory utilization. The native owner and submitter need the updated SDK
contract; model lifecycle and cache ownership stay platform-owned.

The primary scene analysis is a deliberate perception/policy composition using
the two declared models. Cosmos receives one committed selected JPEG per request
and returns two to four factual sentences with thinking disabled. It does not
assign frame IDs or evaluate facility policy. Bind each response to the original
selected frame from its request. Default to two chronological selected frames.
Count every Cosmos image request against the existing twelve-call rolling-minute
budget; cap selected frames by that budget when necessary. Preserve one active
analysis and one latest pending window, minimum admission interval, freshness
expiry and effect-journal replay. Individual frame requests are serial.

The declared primary Nemotron model evaluates the current supervisor goal,
including negation, facility rules and possible physical risks against those
frame-bound descriptions and original capture timestamps. It performs semantic
evaluation, never parsing repair. Historical text is bounded background, never
current evidence. It must not invent motion, people, headwear or frame identities
that the current evidence does not establish. Uncertain evidence cannot certify
absence or a policy violation. Conversation/history behavior remains intact. Use the dedicated scene-decision
prompt, not image-viewing instructions. A requested physical condition does not
require proof of a site-policy breach. Supply the current goal beside the current
frame evidence and require consistent helmet/head-visibility/facility findings.

Each Cosmos response must stop normally with nonempty final content and no
private-reasoning tags. Limit it to512 tokens. Limit the semantic decision to1800
tokens; dynamically reduce component ceilings so their total never exceeds the
existing4096-token scene allowance. The vision request deadline remains300s and
the primary model deadline60s; smaller platform limits win. Preparation and
lifecycle stay platform-owned. Malformed, truncated, unsupported or capacity-
failed inference is explicit, never a successful clear scene. Do not dispatch
another inference to repair output or salvage a partial JSON object.

The primary model receives one strict JSON Schema requiring the ten typed
observation fields, list-valued uncertainties, lowercase severity, configured
facility-rule IDs and valid original selected-frame indices. Validate the full
schema before normalization, then retain the existing goal, helmet, facility,
forecast and provenance validators. Missing evidence references remain errors;
never invent them from a different finding. The generation schema omits
uniqueItems for decoder portability; downstream validation rejects duplicate
indices. Every free-text field and array is bounded, including the existing
80/80/60/160/160 detection limits. Invalid output identifies its failed field
without logging response content. Private reasoning is excluded from publication.

Ask for the compact ten-field decision and at most two forecasts. Describe
visible posture, hand actions, objects, interactions and changes across cited
frames only to the extent supported by the Cosmos evidence. Quiet scenes may
be brief; unclear actions remain uncertain. Normalization supplies legacy report
fields. Never drop provenance or uncertainty to meet the token target.

Prepare the declared vision model through the existing SDK manager alongside
camera/person sampling. Do not admit a caption until preparation and required
image capability checks succeed. Pending evidence and goal revisions keep
refreshing during preparation. Report preparation, failure and active inference
separately, with caption.model_prepare timing. Preserve the single active request
and all existing admission, evidence and deadline rules. Camera failure never
becomes model readiness, and stopping prevents late preparation from opening
admission.

Keep the full scene activity account once; generation bounds summary to160,
helmet evidence to160 and facility evidence to200 characters. Do not duplicate
one person's continuing appearance as multiple detections, or present a current
helmet finding as a forecast. The live default recalls one complete prior
Markdown account; retained history and the twelve-account history/Q&A limit are
unchanged. Busy scenes may exceed the450-token target to preserve evidence.

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
browser action endpoint. Show fresh detector counts, last confirmed sampled person
presence and caption processing time independently of completed scene reports.
Place live video first, compact 11–12px status rows below, then an expandable
latest analyzed snapshot. Completed scene understanding, risk forecasts and model
uncertainties appear above that snapshot while monitoring continues; empty model
lists are reported as such, never as proof that the scene is safe or certain.
The completed account remains visible during the next inference. Render model
text as text, retain capture time and qualify recorded demo playback.
Display capture and completion times distinctly. Freshness uses completion time;
an active inference is processing until its deadline, not stale merely because
its captured frames are older than60seconds. Surface resident overwritten plus
expired window counts instead of the obsolete report-only sampling counter.
Short local times retain full timestamps in tooltips.
Long values must wrap within narrow panels. Preserve detailed scene accounts in
latest-status replies and confirmed goal notices rather than the short metric
preview. Blueprint guidance ends goal-change replies after applied receipts and
current analysis readiness; it never holds a turn open for future scene analysis.
Routine progress stays in the workspace. Desktop input and generic activity
indicators remain host-owned and are not overridden by blueprint state.

Completed notices are final SDK exchange records. Only final records are eligible
for the blueprint activity watch; transport receipt never acknowledges review.
Each applied goal revision produces one completed-result message even when its
condition is not confirmed. Medium/high forecasts scoring at least 0.55 with
valid original selected-frame indices can produce separate possible-risk messages.
These retain capture/analysis times, frame references, recording qualification
and human review language, and never become confirmed incidents. The SDK store
deduplicates by run, camera, goal revision and risk label/severity; unchanged
forecasts remain quiet across polling, restart and bounded history rotation.
Apply this reporting policy to arbitrary operator-specified visible conditions.
Preserve the condition and its negation, and keep the existing frame-bound goal
validation; do not add object-specific goal parsers or matching shortcuts.
Never relabel a person-gate event as a verified facility-rule notice or total unique
person count. Bundled demo is an explicitly staged approved MP4, looped
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
credentials or private reasoning enter canonical text memory. get_operator_status exposes the
facility queue/coverage and separate lane health. get_video_history returns up to
twelve complete matching accounts across Job runs; time bounds need timezone.
Video Q&A and summaries use EmbeddingGemma 2 image/text discovery, bounded review
of retrieved saved images and the prepared text model; they never change the goal
or start capture. The chronological get_video_history read retains its text-only contract.
They retain the runtime-prepared text-model binding and generation controls rather
than reapplying catalog model/provider/endpoint defaults. Require structured output,
disable private thinking and retries, and retain the 60-second/1024-token limits
without increasing a smaller runtime allowance.
Preserve citations, capture times, omitted counts and source qualification. No
unique-person/total-appearance claims from repeated samples. Stable Job supervision
and response services remain SDK-owned, including operation receipts and lifecycle.

## Image and text history (5.4)

Every successfully analyzed selected capture and its complete authored account
are published to a separate, camera/source/Job-bound Membrane source corpus.
Binary JPEGs are copied by content hash into the declared Job state resource
before publishing their immutable references. They survive run cleanup. The
local SQLite catalog contains capture bounds, source locators, revision/hash
catalogs and indexing state; it does not rank vectors or duplicate source prose.
Native Membrane validates whole manifests, source ACLs and current revisions,
and performs lexical/vector RRF with the shared EmbeddingGemma 2 identity.
The SDK's merged model catalog and runtime model manager own embedding aliases,
artifact identity, preparation, placement and transport. No alternate CLIP or
caption-only retrieval substitutes for a failed configured visual-history path.

History questions prefilter original capture times and optional current-run scope
before native ranking. Image and complete-account hits join into one observation
group; captions remain whole under the context-byte allowance. Up to twelve
groups are admitted, with explicit omissions/pending indexing and bounded native
candidate coverage. More than 5,000 scoped source identities requires a shorter
interval. Cross-run restoration revalidates Job originals; camera/source/Job
changes cannot widen the corpus. Images are size/hash verified when loaded and
again before model dispatch. Missing/changed assets or unavailable embeddings
are explicit failures. Existing text-only records retain the chronological
get_video_history read and are not silently presented as image-indexed history.

The default retrospective review sends at most two retrieved historical images
to the declared vision model, serially in the existing Cosmos slot. The answer
model sees complete original accounts plus capture/hash-bound image descriptions,
never binary media. Each image response must stop normally and pass the existing
frame-evidence validator; failed/truncated results cannot fall through to a text
answer. Review is bounded to 512 tokens/60 seconds per image, respecting smaller
runtime settings. Monitoring admissions and explicit historical reviews share
one process-safe rolling image-request allowance; a busy allowance is explicit.
The retrospective tool never changes monitoring or starts capture. Image
similarity is navigation, not event verification, identity or motion evidence.

visual_memory defaults enabled, max_context_bytes=49152 and max_review_frames=2
(valid 1..4). The source-built engine, Membrane SDK 2.2 and main SDK
1.4.1.dev35 or newer with RuntimeEmbeddings are required. Reprepare an idle Job to adopt
the new bundle. Images have no automatic deletion in this feature; operator-owned
Job storage retention/deletion remains authoritative. Indexing and image review
have separate memory.visual_index and rag.image_review measurements. No live
camera, model-quality or throughput qualification follows from offline tests.

## Measurement and acceptance

See BENCHMARKS.md for exact boundaries. Add caption.preprocess timing; keep frame
age, person preparation/inference/policy, caption queue/dispatch/model wait, Cosmos frame evidence, semantic decision and complete analysis,
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


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Explicit aliases, camera knowledge and restrictive control rules keep their existing bounded Job memory path and receipts. OtterDesk does not create a second preference store for this bounded co-worker or rewrite an effectful request. Ordinary chat is not learned.

Use timestamped saved camera Markdown and existing Membrane observation retrieval. Recorded demo playback is historical demonstration, not a live site event. A moving preview does not prove scene analysis. Missing observations do not mean a clear or safe scene. Stream addresses and credentials belong in secure fields. Monitoring goals, camera notes and bounded domain memory retain their existing authority. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.

## Deterministic desktop goal control

OtterDesk may call the existing monitoring tool directly for an explicit goal
editor or Watch from now choice, without an LLM tool call. Preserve the exact
condition and negation. A find-if request without clear time scope offers Watch
from now and Search saved footage before dispatch. Explicit past-time questions
remain history reads. Queued, applied and analyzed states stay separate; reconnect
checks the saved operation instead of resubmitting a mutation. The existing MCP
contract, readiness, Core steering and inference pipeline remain authoritative.

Cold starts use an explicit 4 GiB KV-cache allocation for the pinned Edge recipe,
32K context and one sequence. Cache sizing must not depend on a dynamic
free-memory delta while the co-resident text model loads or unloads. Model startup
must pass before admitting a frame; a failed startup remains an explicit error.
