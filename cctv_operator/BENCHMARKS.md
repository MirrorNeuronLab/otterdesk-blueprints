# CCTV pipeline benchmarks

Keep one result per experiment, model, hardware and approved footage. The initial
production detector is **RF-DETR Small for person events**; Medium is prepared
for a controlled comparison. The pipeline records real measurements when it
runs. Empty measurements are not benchmark results.

| Stage | Implementation | Measurement boundary |
| --- | --- | --- |
| `stream.frame_age` | Shared CUDA relay | JPEG publication to detector processing start; excludes sensor/network/decode before publication |
| `person.model_load` | RF-DETR Small/Medium | SHA-256 verification, strict COCO loading, device placement and FP16 setup; cold |
| `person.preprocess` | Pillow | JPEG decode to RGB; RF-DETR's internal resize stays in inference |
| `person.inference` | RF-DETR for person events | Complete `predict`, including internal preprocessing, GPU forward, synchronization and postprocessing |
| `person.policy` | Scene-presence episodes | Persistence, sampled absence, instruction revision and gap handling |
| `person.evidence` | Durable frame artifacts | Frame, episode and bounded notice-preview persistence |
| `notice.publish` | SDK human notice + MCP activity | Durable notice and activity publication; excludes desktop receipt/display |
| `person.capture_to_notice` | Full person lane | First qualifying sampled frame availability to notice publication, including persistence delay |
| `caption.queue_wait` | Independent caption admission | Window offered to window claimed by sampler |
| `caption.dispatch_wait` | Core | Claimed batch to caption handler load |
| `caption.model_queue_wait` | Single Cosmos slot | Caption handler waiting for the model slot |
| `caption.inference` | Cosmos video captioning | Complete bounded model request and final-answer normalization; errors measured separately |
| `memory.recall` | MN / Membrane | Complete caption context retrieval before a new caption |
| `memory.write` | MN / Membrane | Authored caption publication and durable receipts/Markdown |
| `caption.capture_to_memory` | Full caption lane | Last selected frame availability to successful enabled memory publication |
| `rag.retrieve` | MN / Membrane | Historical caption hydration and citations |
| `rag.answer` | Configured primary text model | Answer generation and citation validation |
| `person.coverage` / `caption.coverage` | Sampling/admission | Skipped relay revisions and replaced caption windows; these are counts, not model latency |

The stage ledger is bounded to the newest `benchmarks.max_samples` records
(10,000 by default). p50/p95/max use successful retained measurements only;
errors, cold starts and skipped coverage remain visible separately. Intentional
downsampling also counts skipped relay revisions. Samples with different model,
weights, hardware, resolution, configuration, domain implementation, confidence threshold or footage
cohort are not pooled. The first prediction is cold; subsequent predictions are
warm. Published RF-DETR TensorRT timings are not comparable to this PyTorch FP16
adapter without reproducing that engine, input and hardware.

Read `get_pipeline_benchmarks` from the active co-worker, or export locally:

```bash
python3 payloads/services/benchmark_cctv.py summary \
  --run-dir /absolute/path/to/run --output /absolute/path/to/stages.json
```

Frame times are **worker frame availability**, not camera sensor times or the
original recording date. The demo loops recorded footage. Notice latency does
not assert that OtterDesk or the OS displayed the notification. Memory timing
does not measure answer correctness. Benchmarks contain no camera URLs, images,
captions, prompts or credentials.

## Compare Small and Medium on labeled footage

Use approved local JPEGs and an independently labeled manifest. Paths are
relative to the manifest and must remain inside its directory. Timestamps are
strictly increasing footage seconds. Label every selected frame; optional event
intervals define scene-presence episodes independently of the detector output.

```json
{
  "frames": [
    {"path": "frames/0001.jpg", "timestamp": 0.0, "person_present": false},
    {"path": "frames/0002.jpg", "timestamp": 0.2, "person_present": true},
    {"path": "frames/0003.jpg", "timestamp": 0.4, "person_present": true},
    {"path": "frames/0004.jpg", "timestamp": 0.6, "person_present": false}
  ],
  "person_events": [{"start": 0.2, "end": 0.4}]
}
```

Run inside the prepared CUDA worker environment. Replay never downloads models,
reads a live camera or sends notices:

```bash
python3 payloads/services/benchmark_cctv.py replay \
  --dataset /approved/dataset/labels.json \
  --models small medium --threshold 0.55 --warmup 5 \
  --output /absolute/path/to/new-comparison
```

Use a fresh output directory per comparison. It writes `comparison.json`, each
model's `replay.json`, and stage ledgers. SHA-256 covers the manifest and frame
contents. Models run sequentially on the same GPU. Warmup is excluded from
measured inference; preparation remains a cold measurement. The report preserves
threshold, warmup and episode policy, and includes:

- Frame-presence precision/recall and true/false positives/negatives.
- Matched/missed/false episodes, if independent event labels were supplied.
- p50/p95 confirmation delay on the footage timeline, separately from model time.
- p50/p95 inference and policy timing, with hardware, package and checkpoint.

This replay is an accuracy and adapter comparison. It does not simulate real-time
backpressure or measure live notification delay. Then run each candidate on the
same source at the same requested FPS, with concurrent Cosmos captioning, and
compare the live person/caption/notice/memory stages plus skipped coverage. Use
`benchmarks.cohort` to distinguish those runs. Validate caption factuality and
temporal evidence, RAG citation correctness, and actual desktop receipt separately.

Keep an experiment record with footage fingerprint, labels, model/checkpoint,
hardware/software, input resolution/FPS, threshold/episode policy, concurrent
load, error/skip counts, recall/false-event rate and p50/p95 latency. A faster
model with unacceptable missed events is not a successful replacement. RF-DETR
Small/Medium are implemented; future YOLO or RT-DETR adapters must satisfy the
same `load`/`detect` contract and labeling protocol before comparison.

## Validation status

Both pinned checkpoints were verified on 2026-10-08 against RF-DETR 1.11.2:
all learned tensors loaded strictly, and both models predicted a synthetic black
frame with network requests disabled. This was a CPU contract smoke test with
PyTorch 2.14.1, not a CUDA throughput or person-accuracy benchmark. The adapter's
CUDA FP16 path, concurrent Cosmos load, labeled camera accuracy and actual
notification receipt require measurements in the prepared worker environment.
No latency or accuracy figures are claimed from that smoke test.

Primary model reference: [RF-DETR](https://github.com/roboflow/rf-detr).
