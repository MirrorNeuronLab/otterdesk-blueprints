# CCTV Operator

Version 3.1 runs one approved camera stream per Job on an NVIDIA CUDA node.
Choose a factory or hotel review profile, see timestamped sampled observations
and frame-linked human notices, and ask questions about retained camera history.
Risk forecasts remain hypotheses for review. This is not a certified safety or
security system and does not take physical action.

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
larger/longer sequence settings for an explicit quality comparison. The installed
CLI uses repeated `--set`; it does not accept these files via `--config`.

## Responsive pipeline

One persistent CUDA FFmpeg relay feeds the preview, an independent resident
RF-DETR person lane and a separate caption sampling lane. Rate selection precedes
CUDA resize and host download. The default shared relay is 960 pixels wide at
8 FPS; source aspect ratio is preserved. RF-DETR Small requests 5 FPS and retains
two-hit confirmation, sampled-absence rearming and explicit gap handling.
No CPU decoder, replacement detector or demo-source fallback is used.

Default caption policy:

- 4 candidate FPS; 1.5-second pre-roll and 0.5-second post-roll; up to eight
  chronological selected frames, resized within 768 pixels without upscaling.
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
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.26 --web-ui \
  --set video_source.demo_file=/absolute/path/on/mini/to/approved-test.mp4
```

The default demo path is `/Volumes/128GB/videos/nv-warehouse-4cams/Camera.mp4`.
It must exist on the submitting machine, be nonempty and fit 512 MiB. The SDK
stages it; MediaMTX and a looping FFmpeg publisher run in the shared worker.
The Web UI service owns the publisher; sampling tick cleanup cannot stop it.
Demo capture timestamps describe recorded playback, not a current facility event.
No host FFmpeg, runtime reset or reinstallation is required.

For an approved hotel camera:

```bash
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.26 --web-ui \
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

Monitoring commands carry command IDs and revisions through Core's declared
steer_monitoring input. Queued, applied and analyzed are separate states. A late
old-goal result can remain in history but cannot notify under a newer revision.
Acknowledging a notice records review; transport delivery does not acknowledge it.
The stable Job response/MCP service can answer capability questions while stopped;
a question does not start the monitor. No runtime/SDK/skill code changes are needed
for this blueprint revision.

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
evidence. The 2026-10-18 edit had offline checks only pending Spark restart and an
available approved demo/camera input.

See [SPEC.md](SPEC.md) for the contract and [BENCHMARKS.md](BENCHMARKS.md) for
measurement boundaries. Source bundles use canonical blueprint/v1 documents;
workflow topology, execution/model recipes, contracts and defaults remain separate.
