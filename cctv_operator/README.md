# CCTV Operator

Version 5.1.1 runs one approved camera stream per Job on an NVIDIA CUDA node.
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

## Factory and hotel setup

`site.profile` selects `factory`, `hotel` or `custom`. Factory is the default.
Leave `inputs.payload.monitoring_goal` blank/omitted to use the selected profile's
goal. An explicit goal or a Chat steering instruction replaces that notification
goal. Clearing Chat steering restores the configured/profile goal. Profile rules
remain visible as supplementary review material; omitted rules stay unexamined.

| Profile | Review rules | Limits |
| --- | --- | --- |
| Factory | Visible travel-path obstruction; person near moving industrial equipment; clearly visible uncovered head | No invented speed/distance, collision certainty, PPE requirement or compliance verdict |
| Hotel | Visible travel-path obstruction; person appears down on the floor; possible spill/floor hazard | Approved public/common areas only; no diagnosis, inferred fall, identity or private-room monitoring |
| Custom | Operator's explicit visible condition | No built-in facility rule assumptions |

Each finding identifies observed, possible or not_observed status, supporting
selected frames, model confidence, review action and the operator-supplied
`site.review_owner` (default Unassigned). Motion claims need at least two frames;
an uncovered-head observation needs a same-frame visible uncovered head. Frame
binding verifies provenance, not the truth of the model's interpretation.
The Markdown report has a facility review queue and unexamined-rule coverage.
Possible findings and forecasts do not become confirmed-event notices.

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
  --set site.review_owner='Site reviewer'
```

The default input is the live retail RTSP stream configured in
`config/default.json`, using the external source profile and camera ID `retail`.
No local video file is required or staged. The NVIDIA worker must be able to
reach the stream. OtterDesk's sample setup uses this same live stream; choosing
your own input requires an approved stream URL through the secure source field.

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
complete history and a 4096-token answer allowance. Its request deadline remains
300 seconds. Truncated, malformed or unsupported results are errors, not clear
scenes. Private reasoning never enters reports or history.

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

The read-only job-scoped Web UI shows live MJPEG and the latest analyzed snapshot.
It makes no browser steering requests and never exposes camera URLs/credentials.
The generic SDK proxies the OS-selected worker listener through the Job UI route.
An authenticated loopback MCP relay has its own owner-only private endpoint
artifact; it is never a public browser endpoint. No fixed host MCP port is used.

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

## Block composition (5.1.0)

The camera/UI owner uses the SDK monitored-service block. Ingress now uses a
direct `domain.monitor_ingress:process` event hook: SDK owns immutable scoped
state/replay, and Core resolves the start/steering ports and logical completion.
The old ingress script is removed. The submission validator and native start
share one source-validation policy; completed replay never probes the camera again.
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
