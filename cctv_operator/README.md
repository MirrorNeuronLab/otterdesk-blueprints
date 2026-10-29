# CCTV Operator

Version 5.3.6 runs one approved camera stream per Job on an NVIDIA CUDA node.
Choose a factory or hotel review profile, see timestamped sampled observations
and frame-linked human notices, and ask questions about retained camera history.
Risk forecasts remain hypotheses for review. This is not a certified safety or
security system and does not take physical action.

The live camera/UI owner now uses `mn.blocks.monitored_service@1` through
`extensions/blocks.json`. Core retains the same entrypoints, routing and four
processing phases. Domain hooks own camera resources and first-frame readiness;
the shared block owns periodic listener health, durable checkpoints, replay and
cleanup after partial startup or stopping. Native event workers require matching main
SDK `>=1.3.61.dev27,<2`, blocks `>=1.3.61.dev27,<2`, common `>=1.3.61.dev25,<2`, the coordinated Core
event/publication protocol, and supervised-service agent `>=1.3.61.dev5,<2`.
The migration is qualified by offline listener and process-group tests; the
historical Spark measurements below predate this path.

The Web UI claim uses the SDK's monitored-service lifecycle. The SDK supplies
execution/run identities and the current service generation; CCTV supplies only
its listener, title and presentation metadata. The handle becomes Running after
startup health succeeds, and stopped or failed on cleanup. Reprepare existing Job
definitions to load this revision; a runtime reset is not required.

## Factory and hotel setup

Chat introduces the monitoring task, asks for the secure **Video stream URL**,
and explains camera checks, model preparation and the progress panel before
startup. The field uses a short label so the saved answer reads
`Video stream URL: Saved securely`. `extensions/ui.json` binds the setup AI to
`payloads/prompts/setup.md`; the installed `knowledge/user_manual.md` supplies
the bounded conversation model's product guidance. Setup drafts never establish
readiness or authorize a monitoring action.

Status replies separate camera connection, person detection and scene analysis,
with the observed stage and a useful next action. Goal-change receipts explain
queued, applied and analyzed states. Empty history replies explain the missing
evidence and how to check monitoring or choose another interval. History answers
request short Markdown paragraphs and timed bullets while retaining citations.
The desktop owns its transient Preparing indicator; this blueprint supplies the
surrounding guidance and domain replies without changing runtime or UI code.

Conversation validation on 2026-10-27: 62 focused guidance, status, history,
MCP and manifest checks pass. The real `--fake-llm --fake-skill` GUI scenario
reached startup and loaded the workspace; its overall gate failed on a runtime
`prepare_job_update` / `MN_INVALID_ARGUMENT` receipt and a desktop pause-state
conflict. The test-owned Job was cleaned up. Real Nemotron probes confirmed
useful startup guidance, selection of the readiness read tool, clarification for an unspecified goal,
and a cited synthetic history answer retaining both capture times and sampling
limits. Setup tool-call delivery remains inconsistent in direct model probes,
and the Job planner can still claim to have checked history without selecting
the read tool. Blueprint wording does not enforce that runtime boundary; those
remain acceptance limitations. No runtime source, model settings or desktop
source was changed.

The catalog run had 1,541 passes and 39 skips. Its three initial failures passed
on a focused rerun after adding the missing CLI source to the temporary test
environment and finishing the source edits that overlapped the long run. The
final 62-check conversation/MCP/manifest rerun passed. `git diff --check` passed.

`site.profile` selects `factory`, `hotel` or `custom`. Factory is the default.
Leave `inputs.payload.monitoring_goal` blank/omitted to use the selected profile's
goal. An explicit goal or a Chat steering instruction replaces that notification
goal. Clearing Chat steering restores the configured/profile goal. Profile rules
remain visible as supplementary review material; omitted rules stay unexamined.

| Profile | Review rules | Limits |
| --- | --- | --- |
| Factory | Group presence; visible travel-path obstruction; person near moving industrial equipment; clearly visible uncovered head | No invented speed/distance, collision certainty, PPE requirement or compliance verdict |
| Hotel | Group presence; visible travel-path obstruction; person appears down on the floor; possible spill/floor hazard | Approved public/common areas only; no diagnosis, inferred fall, identity or private-room monitoring |
| Custom | Operator's explicit visible condition | No built-in facility rule assumptions |

Each finding identifies observed, possible or not_observed status, supporting
selected frames, model confidence, review action and the operator-supplied
`site.review_owner` (default Unassigned). Motion claims need at least two frames;
an uncovered-head observation needs a same-frame visible uncovered head. Frame
binding verifies provenance, not the truth of the model's interpretation.
The Markdown report has a facility review queue and unexamined-rule coverage.
Possible findings and forecasts do not become confirmed-event notices.

Both facility profiles can notify from the first analyzed sample showing two or more
people together, including a stationary group already present when monitoring
starts. No helmet issue or other hazard is required. The notice says a group is
visible; arrival is claimed only with sampled before-and-after evidence. Repeated
views stay quiet until a confident absence rearms the rule and its cooldown ends.
If several new rules match, the highest-priority finding is reported first; other
findings remain eligible for their own notice on subsequent analyzed samples.
This uses the existing Cosmos analysis path and does not bypass model latency.
Reprepare existing Job definitions to load the updated rules and prompt; an explicit
saved goal or Chat instruction still takes precedence over profile defaults.

Optional `site.zones` contains up to twelve `id`, `name`, `bounds` objects, with
normalized full-view `[x1,y1,x2,y2]` rectangles. These guide interpretation; they
are not metric calibration, privacy masks or enforced image crops. Supply only
approved views. Avoid private hotel rooms/bathrooms and choose retention/access
rules appropriate to the site. No identity, protected traits, emotion, intent,
injury diagnosis or legal compliance is inferred.

`examples/factory-monitoring.json` and `examples/hotel-monitoring.json` are mergeable
blueprint configuration examples. `examples/detail-review.json` preserves the
longer sequence settings for an explicit quality comparison.
`examples/smaller-media.json` selects a 960-pixel relay and 768-pixel captions for
sites that independently validate the loss of distant/small-object detail. The installed
CLI uses repeated `--set`; it does not accept these files via `--config`.

## Responsive pipeline

One persistent CUDA FFmpeg relay feeds the preview, an independent resident
RF-DETR person lane and a separate caption sampling lane. Rate selection precedes
CUDA resize and host download. The default shared relay is 1280 pixels wide at
8 FPS; source aspect ratio is preserved. RF-DETR Small requests 5 FPS and retains
two-hit confirmation, sampled-absence rearming and explicit gap handling.
No CPU decoder, replacement detector or demo-source fallback is used.

Default caption policy:

- 4 candidate FPS; 1.5-second pre-roll and 0.5-second post-roll; up to eight
  chronological selected frames, resized within 896 pixels without upscaling.
- Person confirmation triggers a sequence. Periodic scene audits inspect static
  hazards even without a person: first after a complete two-second window, then
  after fifteen seconds without another offered window. Steering requests can
  request the next eligible audit. Audits never claim RF-DETR saw a person.
  A newly confirmed person episode starts its short post-roll immediately even
  after a recent audit; continuing presence follows the normal sampling cadence.
  The active-request, minimum-admission and per-minute limits still apply.
- One active Cosmos request and one latest pending window; five-second minimum
  admission interval and twelve admissions/minute maximum. Actual throughput is
  limited by measured model, Core and memory latency, not those ceilings.
- Unclaimed windows older than ten seconds expire with a counter. A stale requested
  window retains its command for fresh evidence. Durable completion releases the
  active slot; lost completion is exposed as stalled without overlapping calls.

JPEG preparation and batch persistence cannot hold the person-signal lock.
Stale camera frames do not advance person episodes or establish absence.
Skipped/expired windows, frame age, preprocessing, queue, dispatch, model-slot,
model inference and memory timings remain separate in `benchmarks/stages.sqlite3`.
Worker timestamps start at relay availability; sensor/network/decode latency before
that is not measured. These settings reduce preparation work and configured wait;
they do not guarantee model latency, recall or end-to-end response time.

Smaller frames can lose distant/small-object detail; short windows can miss motion.
Compare responsiveness and the explicit detail profile on labeled site footage
before choosing production settings. More frequent admissions cannot make a slow
model sustain that rate. This is a sampled single-camera service; use a separate
Job per approved camera, and measure shared-GPU capacity. Multi-camera tracking,
metric distance/speed, safety-rated alarms and calibrated risk probabilities are
not implemented.

## Run on Spark

The blueprint still hard-requires one NVIDIA CUDA GPU with 49,152 MB GPU/unified
IGP memory. SDK admission owns unified-memory detection and single-node placement;
a Mac does not qualify. The sampler, inference, reports and Web UI share the
selected DockerWorker. Pin Spark explicitly for validation:

```bash
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.32 --web-ui \
  --set video_source.uri=rtsp://camera.example/approved-stream \
  --set site.review_owner='Site reviewer'
```

There is no built-in stream URL or live sample. Each new OtterDesk hire asks
for an approved RTSP or RTMP URL through the required secure input field.
Monitoring stays unavailable until that answer is saved. Saved co-workers keep
their configured source. The NVIDIA worker must be able to reach the stream.
Hiring prepares the co-worker without connecting to a camera; the native monitor
validates the supplied source before publishing a ready session or sampling.
No local video file is required for an external stream.

Recorded playback remains an explicit option:

```bash
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.32 --web-ui \
  --set video_source.profile=bundled_demo \
  --set video_source.uri=rtsp://127.0.0.1:8554/cctv-demo \
  --set video_source.demo_file=/absolute/path/on/mini/to/approved-test.mp4
```

The selected MP4 must exist on the submitting machine, be nonempty and fit
512 MiB. The SDK stages it only for `bundled_demo`; MediaMTX and a looping FFmpeg
publisher run in the shared worker. The Web UI service owns the publisher;
sampling tick cleanup cannot stop it. Demo capture timestamps describe recorded
playback, not a current facility event. No host FFmpeg, runtime reset or
reinstallation is required.

For an approved hotel camera:

```bash
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.32 --web-ui \
  --set site.profile=hotel \
  --set site.review_owner='Duty manager' \
  --set video_source.profile=external \
  --set video_source.uri=rtsp://camera.example/approved-common-area
```

Use OtterDesk's secure source input for credentials. Never paste credentials into
commands, reports or Chat. External RTSP/RTSPS/RTMP/RTMPS must be reachable from
Spark; a submitter's loopback address is not a remote camera. Invalid input,
unavailable stream, CUDA/model failure and insufficient context remain explicit.
No external source falls back to the demo. One configured camera per Job.

Cosmos3 Nano Reasoner 1.7 remains the declared Docker/NVIDIA NIM vision model;
Nemotron 3.5 Lightning remains the text conversation model. Preparation and
lifecycle are SDK-owned. The exact model recipe, resource requirements and
matching package versions remain in execution.json/dependencies.json.
Initial NIM installation needs the existing runtime's NGC credential environment;
the blueprint does not install or reconfigure the runtime. Cosmos receives the
selected sequence via MP4/video_url at 4 FPS, real selected timestamps, optional
complete history and a request ceiling of 4096 output tokens, subject to the
runtime gateway's smaller per-response and hardware limits. Its request deadline remains
300 seconds. Truncated, malformed or unsupported results are errors, not clear
scenes. Private reasoning never enters reports or history.
Routine monitoring requests compact JSON directly, without a reasoning-template switch,
using the [Cosmos3 NIM direct-answer request contract](https://docs.nvidia.com/nim/vision-language-models/1.7.0/examples/cosmos-reason3/api.html).
Requests include a strict JSON Schema for the ten-field observation, with
array-valued uncertainties, lowercase risk severity and frame references bounded
to the selected evidence. All free-text fields are bounded, including detection
position/activity, so repeated detail cannot consume the entire answer budget.
The deployed NIM must support JSON-schema response_format;
an unsupported request fails explicitly. Semantic evidence validation remains in
place. This fixes the normally stopped response that supplied a scene account but
encoded uncertainties as a string and severity as `Low`, which previously surfaced
as a misleading missing-scene error. Reprepare an idle saved Job before starting
this revision; frozen requests in existing runs retain their original contract.
Cosmos video input uses complete temporal frame pairs. An odd selected window
repeats its final frame only in the encoded transport; the prompt identifies
that duplicate and restricts evidence references to the original selected frames.
Capture timestamps, selected counts, hashes and reports retain the original
evidence. This prevents the timestamp/video-length failure seen with five-frame
windows. Reprepare the saved Job from this blueprint revision before a new run;
existing failed runs and frozen inference requests remain unchanged.
The prompt requests ten evidence-bearing fields and at most two forecasts,
targeting about 900 output tokens. Person activity receives two to six concrete
sentences (up to 1800 characters), describing visible posture, movement, hand
actions, objects and interactions, with selected-frame references and uncertainty.
Quiet scenes can remain brief. The summary and other evidence stay concise;
no reasoning or larger model allowance is requested. The report adapter retains legacy
fields; it does not ask the model to repeat the same scene in each one.
The final JSON object is the answer boundary: a normally stopped Cosmos reply may
omit its closing answer tag or wrap the object in a JSON fence. The parser accepts
only the complete object; unfinished reasoning, truncated output and trailing prose
remain errors. It never recovers a partial object or repeats inference to repair it.

### Response-contract verification on 2026-10-28

All 280 CCTV checks pass for 5.3.2. A real approved-stream run on Spark produced
a normally stopped Cosmos scene account, typed uncertainty/forecast lists, a
published report and analyzed snapshot, and persisted camera Markdown. The
owner-node Job MCP history tool retrieved that account with a citation. The
cold request took 150.5 seconds, including model preparation. Generation keeps
the existing token/deadline limits and excludes XGrammar's unsupported uniqueItems;
the domain validator still checks evidence uniqueness.

That initial run exposed a separate continuous-dispatch failure: Core admitted a
second batch without dispatching it. Core commit e323bfa fixes classification of
the compiler's `flow.dynamic: {"enabled": false}` service form. On that revision,
the approved-stream run published 11 successive scene accounts and evidence
snapshots. The first model request took 171.6 seconds; subsequent requests varied,
so delayed-analysis health remains distinct from the last completed account.

Version 5.3.3 adds completed analysis to the panel. Its deterministic Chromium E2E
covers successive SSE results, reconnection, delayed processing, text escaping and
wide/narrow resizing. All 280 CCTV regressions pass together. Catalog-wide collection
still references removed microduck, and a catalog-category test references removed
financial_advisor. Initial MCP reads through mini also failed with ExceptionGroup
while owner-node reads succeeded. Desktop active-run chat policy is separate from
the completed scene account displayed in the panel.

## Notices, risk and history

A profile notice needs an observed rule with selected-frame evidence, sufficient
confidence and that rule's cooldown. Distinct newly observable rules can notify
independently. Only a sufficiently confident not_observed sample rearms that
rule; possible, omitted, missing or failed observations cannot clear it.
Custom goals retain their goal-event checks and explicit operator direction.
All notices include capture time and bounded immutable evidence; a human confirms
any response. Slack remains off unless explicitly configured and authorized.

Predictions name supporting selected frames, qualitative horizon, severity and
recommended review. Model scores are uncalibrated, not probabilities. Forecasts
are never counted as incidents or asserted as future certainty. Reports/history
retain capture interval, recording qualification, active instruction and omissions.

`get_operator_status` reads the latest understanding and facility queue plus
separate person/caption health. `get_video_history` retrieves up to twelve complete
matching authored Markdown accounts across Job runs for the same camera/source,
with timezone-qualified after/before bounds. `answer_video_question` and
`get_video_summary` use the text model and complete authored history, never another
image interpretation. Their correlated get_operation_status result updates the
original turn. Missing history is not zero activity. Repeated sightings cannot
establish unique people or total appearances. Knowledge examples are synthetic
reference material, never observations.

History questions and summaries retain the text model, provider, endpoint,
credentials and generation options selected during runtime preparation. Blueprint
defaults do not replace a prepared gateway route. These requests remain bounded
to 60 seconds and 1024 answer tokens, with retries and private thinking disabled.
Smaller runtime request limits remain in force.

Monitoring commands carry command IDs and revisions through Core's declared
steer_monitoring input. Queued, applied and analyzed are separate states. A late
old-goal result can remain in history but cannot notify under a newer revision.
Acknowledging a notice records review; transport delivery does not acknowledge it.
The stable Job response/MCP service can answer capability questions while stopped;
a question does not start the monitor. Install the declared shared packages
before running this blueprint revision.

## Outputs and operations

### Change the Cosmos focus in Chat

Ask for a visible subject or condition, including a question such as “can you
focus on if the person wearing the safety helmet”. This changes the prompt for
future Cosmos samples; it does not require a PPE policy or a visible head before
the prompt can be applied. Positive and negative conditions remain distinct.
Only an unspecified goal such as “watch for problems” needs clarification.
Past-event questions leave the goal unchanged. An applied receipt confirms the
prompt revision, separately from the next analyzed sample.

Version 5.3.4 revises the blueprint tool description used by the desktop's existing
interpreter and removes the visual prompt's blanket missing-helmet interpretation.
Version 5.3.5 launches the Python control sidecar directly, allowing normal SDK
preparation to install its declared run-input client dependency. A shell wrapper
previously hid Python from preparation and left steering unable to import it.
Version 5.3.6 sends steering to Core's public execution ID. The private MCP
endpoint and artifacts remain bound to the separate physical workflow ID,
including after resume. Sending the physical ID to SendRunInput was rejected
because it is not the public execution record.
An already prepared Job retains its installed contract until reprepared from this
revision. No desktop, SDK, runtime, detector or model code changes are required.

The read-only job-scoped Web UI leads with live MJPEG, followed by compact
People, Scene analysis and Monitoring status rows in 11–12px system type.
Completed scene understanding, risk forecasts and uncertainties appear below
status while monitoring continues, followed by the expandable analyzed snapshot.
An empty forecast or uncertainty list means the model returned none for that
sample; it does not establish safety or certainty. The completed account stays
visible while the next sample is processing. The snapshot's short
local analysis time discloses the complete timestamp in a tooltip. Warnings
remain beneath status, and all rows fit narrow workspace panels. A visible
preview does not imply that person detection or scene analysis is healthy.
Fresh person-detection counts and the last confirmed presence time appear before
Cosmos finishes. Scene-analysis progress is separate. These sampled detections are
not unique-person counts or verified facility-rule notices.
It makes no browser steering requests and never exposes camera URLs/credentials.
Detailed activity survives in saved history, latest-status replies and confirmed
goal notices, including their capture time and recording qualification.
Blueprint conversation guidance keeps routine long-running progress in this
workspace and ends a goal-change reply after its applied receipt and current
analysis readiness. It does not wait for a future scene in that turn. Desktop
composer and generic activity indicators remain controlled by the host app.
The generic SDK proxies the OS-selected worker listener through the Job UI route.
An authenticated loopback MCP relay has its own owner-only private endpoint
artifact; it is never a public browser endpoint. No fixed host MCP port is used.
The sidecar uses Core's physical workflow run identity to locate and verify that
endpoint, including after resume; a submission label is not the current run.

Authoritative run outputs are on SDK shared run storage. The default
`~/Downloads/cctv-operator` is an additional host copy. Keep the run package for:

- cctv_report.json / cctv_report.md / final_artifact.json;
- events.jsonl / monitoring_state.json / caption_schedule.json;
- frame_batches/<batch>/batch.json and selected hashed JPEGs;
- latest_analyzed_frame.jpg / .json and bounded immutable notice images;
- runtime_memory receipts, prepared context_sources/outputs Markdown and benchmark ledger.

Job knowledge, RAG and state remain isolated and persist across runs. Cleanup of a
run never clears Job data. Standard mn.mcp.supervision.v1 owns lifecycle controls;
stop the Job to stop its stream publisher and services. Do not reset a runtime to
repair a blueprint. Inspect get_pipeline_benchmarks or use the summary/replay
commands in [BENCHMARKS.md](BENCHMARKS.md).

Service lifecycle checkpoints occur every 60 seconds and are bounded to 64 MiB;
camera/person/caption timing remains independent. Capacity exhaustion stops with
cleanup and retains its evidence. Plan an explicit service replacement/rotation
before exhausting that budget. Pause/resume retains completed checkpoints and
reconstructs listeners without replaying completed camera processing.

## Acceptance before customer deployment

Run the offline catalog/blueprint tests, then a real Spark run on approved footage.
Verify CUDA decode/resize, fresh frames, actual detector/model calls, one active
caption, durable reports, history citations and notice evidence through completion.
Measure cold/warm p50/p95, failures, skipped coverage and actual operator receipt.
Use independently labeled factory/hotel events, hard negatives, distant/occluded
people, lighting changes, motion and outages. Report per-rule misses, false notices
per camera-hour and precision/recall with sample counts; no synthetic fixture or
faster preprocessing proves customer accuracy. Agree site-specific latency and
recall targets before deployment. Human review must confirm useful recommended
actions and the selected evidence. Do not claim production readiness without that
evidence.

### Verification on 2026-10-18

Spark was rebooted and reconnected at 10.0.4.32. CUDA relay and the pinned RF-DETR
checkpoint ran on its NVIDIA GB10 against the approved warehouse recording.
Across eight sampled frames, warm complete person-prediction medians were 10.3ms
at 1280 pixels and 8.8ms at 960 pixels. One sampled count differed; no independently
labeled recall/precision claim follows. Four-second offline relay medians were
690.7 ms and 683.0 ms respectively (three trials, including cold startup). These are
stage timings, not real-time event-to-notice latency. Keep 1280/896 as defaults;
the small measured gain does not establish that losing image detail is acceptable.
The shorter sequence, post-roll and scheduling changes remain enabled.

Full workflow submission reached a prepared worker but Spark Core rejected the
current typed response/MCP contract during CreateJob. Job reconciliation returned
not found. No accepted Core run, Cosmos output, published report, history round
trip or operator notice was produced. The blueprint keeps its declared native
contract; no compatibility shim, runtime upgrade or model-registry change was
made. A deployment supporting the declared SDK/MCP contract is required before
the end-to-end gate can pass. Offline checks passed 189 tests; the broader catalog
had 968 passes, 36 skips and one unrelated VC environment-contract failure.

See [SPEC.md](SPEC.md) for the contract and [BENCHMARKS.md](BENCHMARKS.md) for
measurement boundaries. Source bundles use canonical blueprint/v1 documents;
workflow topology, execution/model recipes, contracts and defaults remain separate.

### End-user verification on 2026-10-27

OtterDesk saved an approved LAN stream through Configure and displayed its live
warehouse preview from Spark. RF-DETR and caption capture both ran. The MCP
sidecar remained connected after correcting its lookup and identity check to use
the physical workflow run instead of the submission label. A real, normally
stopped Cosmos response exposed the missing closing-answer-tag case; complete
fenced JSON is now accepted with strict parsing and existing evidence validation.
The visual prompt now declares site findings and forecast frame references in one
output contract. The preview displays analysis failures and snapshot analysis time.

The CCTV offline suite passed 261 checks; 77 focused checks passed after the final
prompt edit. Live verification of that prompt stopped before a model response when
Core reported `coordinator_report_failed` / `message_id_conflict` for an already
acknowledged message. Runtime was not changed. Report/history/notice acceptance
for this revision remains open; preview and detector success alone do not close it.

Follow-up for 5.2.2: the live person detector had confirmed six presence episodes
while the scene result was missing. The saved Cosmos reply had finish_reason=length
at1024 completion tokens, truncating the final JSON. Person count, last confirmed
presence and scene-processing time are now shown independently; the live UI was
verified displaying one detected person. Scene requests use a compact ten-field
direct JSON account and retain strict completion/provenance checks. All264 CCTV
offline checks passed, including compact-account notice evidence. The revised live
run stopped on Core's same acknowledged-message conflict before its model response;
the final compact prompt has not completed a live acceptance run. No runtime source
or operator model settings were changed.

## Block composition (5.1.0)

The camera/UI owner uses the SDK monitored-service block. Ingress now uses a
direct `domain.monitor_ingress:process` event hook: SDK owns immutable scoped
state/replay, and Core resolves the start/steering ports and logical completion.
The old ingress script is removed. Native start validates the configured source;
completed replay never probes the camera again.
Sampling also uses a direct `domain.sampling:process` event hook. It freezes each
instruction and completed resident admission, captures all selected frame bytes
with their hashes, and emits a typed evidence reference. The SDK publishes
immutable files; Core accepts state before delivering their public names. Replay
and receipt repair reuse the same window even after the original files disappear.
The resident queue remembers the latest instruction while public views lag.
Vision and reporting also use direct native event hooks. Vision reads the typed
frame evidence, freezes its request, and uses the shared SDK's durable managed
model call. A raw response receipt precedes interpretation; an uncertain result
cannot dispatch another call or release the resident slot. Known invalid replies
produce qualified errors. Private reasoning stays out of reports/history. Resident
completion uses idempotent per-batch RPC receipts, so an older retry cannot erase
a newer completion. The report worker consumes a scoped observation reference,
keeps cumulative history through immutable references, and publishes the same
JSON, Markdown and final-artifact fields. Camera Markdown uses accepted prior
source bytes; public projections wait for Core acceptance.
All custom processing executables are removed. The offline CCTV/catalog
regression passes 277 cases, including the full 13-blueprint native binding gate.
Installed SDK dev34 / blocks dev33 / common dev30 test candidates execute all
four compiled CLI workers, prepare real synthetic JPEG/MP4 media, and replay in
fresh processes with one claim, one model call, one completion and no early
publication. Resident/model transports are synthetic; a human notice and report
are verified. Core's fake OpenShell event-runner test also passes with the
installed candidates. These are source/test candidates, not published releases.
No live camera/GPU qualification or deployment is claimed for this source change.
Supervision is bounded to 1,000,000 health cycles and 64 MiB of checkpoints;
rotate the service before either bound. Camera timing is independent of the
60-second health interval. OpenShell remains optional for compatible workers,
using the same SDK/Core transport when selected; current Docker placement stays.


## Stage-aware conversation

OtterDesk reads `payloads/prompts/conversation.json` as optional app-owned guidance. It combines this role and stage policy with the pending question, confirmed non-secret setup answers, recent dialogue, selected report and fresh Job state. Short follow-ups retain their topic; a correction does not silently change saved configuration.

Explicit aliases, camera knowledge and restrictive control rules keep their existing bounded Job memory path and receipts. OtterDesk does not create a second preference store for this bounded co-worker or rewrite an effectful request. Ordinary chat is not learned.

Use timestamped saved camera Markdown and existing Membrane observation retrieval. Recorded demo playback is historical demonstration, not a live site event. A moving preview does not prove scene analysis. Missing observations do not mean a clear or safe scene. Stream addresses and credentials belong in secure fields. Monitoring goals, camera notes and bounded domain memory retain their existing authority. Existing submitted runs retain their configuration, evidence and approvals. An idle prepared Job may refresh through the existing conditional API without rehiring, resetting memory or mutating an active run.
