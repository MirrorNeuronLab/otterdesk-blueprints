# CCTV co-worker

The CCTV workspace follows the working sample at
`spark:/home/homer/Sandbox/rt_vlm`. NVIDIA `vss-rt-vlm` 3.3.0 owns DeepStream
video decoding, window sampling and Cosmos3 Edge inference. The co-worker saves
completed streaming captions and supplies a separate, read-only live preview.
Version 6.1 adds goal timelines, window snapshots and image-backed history to the 6.0 NVIDIA streaming blueprint.

## Start

Enter an approved RTSP/RTSPS camera through OtterDesk's secure **Video stream URL**
field, and optionally specify a visible monitoring goal. No camera is included.
Credentials remain server-side; never paste them into Chat or shell commands.

```bash
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.32 --web-ui \
  --set video_source.uri=rtsp://camera.example/approved-stream
```

Refresh the prepared Job when it is idle, then start a new run to use this version. Existing runs retain
their original bundles. The NVIDIA computer needs Docker Compose, the NVIDIA
Container Toolkit, camera connectivity, 48 GiB GPU/unified memory and 25 GB free
disk. The digest in `payloads/vss/compose.yaml` is the sample's ARM64/SBSA image,
targeting DGX Spark. Other hardware requires a matching image and qualification.

## Runtime

Core's native DockerCompose runner prepares and supervises the required NVIDIA
container. Loopback port **8019** is an explicit resource reservation: one CCTV
VSS stack per node. It does not replace the sample on port 8018. Model caches
are external named Docker volumes retained after stop. Initialize them once on
the NVIDIA host before the first hire:

```bash
docker volume create otterdesk-cctv-hf-cache
docker volume create otterdesk-cctv-model-cache
```

The CPU operator runs in Core's prepared Python 3.12 environment through
HostLocal. NVIDIA joins the private runtime network at `otterdesk-cctv-vlm:8000`;
its host-loopback port is reserved for native Compose health checks. MCP and the
workspace use Core-assigned internal ports. The workspace registration advertises
Core's private container interface so the separate UI proxy can reach it.
Camera credentials never enter
Compose. The operator has no container-management capability.

The pinned NVIDIA image contains serialized compilation artifacts that fail
PyTorch's metrics-context check on Spark. The recipe uses vLLM's supported
`VLLM_DISABLE_COMPILE_CACHE=1` setting to compile fresh at startup while keeping
GPU inference and CUDA graphs enabled. Model weights remain cached. See
[vLLM's compilation documentation](https://docs.vllm.ai/en/v0.17.1/design/debug_vllm_compile/).

The SDK `mn.blocks.monitored_service@1` owns the Python operator's lifecycle,
health and checkpoints. Domain hooks own listeners, the streaming request,
preview and publication. First startup can download/compile the model; readiness
waits up to 20 minutes. Use main SDK 1.4.1.dev44 or newer on both submitter and owner for durable inline
Compose activation. Core owns pause/resume/stop and removes only the run's
owned Compose project. No runtime reset is required.

Core's current delivery-v2 contract fences an interrupted long-running invocation
as `invocation_outcome_unconfirmed`. Pausing releases this stack, but resuming that
interrupted run is not qualified; the live test reproduced the fence. Use a new
run after stopping. This rewrite does not bypass Core's uncertain-effect guard.

The direct protocol is `/v1/ready`, `/v1/models`, stream registration,
`/v1/generate_captions` SSE, caption-request cancellation, then stream deletion.
Stop waits for registration to return its stream ID. Failed cleanup retains a
durable ownership lease and blocks another registration. An unknown registration
outcome after a process crash requires reconciliation in NVIDIA; no alternate
camera or inference path is opened. Only resource-in-use cleanup is retried.
After a VSS restart, NVIDIA's exact `BadParameter`/HTTP 400 receipt naming the
missing stream reconciles its saved lease. Other errors still require verified
cleanup before another registration.

## Observations and controls

Defaults analyze eight frames per four-second window at 608×320, with 192 output
tokens, temperature 0.2, no reasoning and no audio. The independent CPU/PyAV
preview updates up to four times per second. Preview success does not prove
analysis success. Model/window latency and capture/receipt times remain distinct.

**Everything** shows the newest completed window first. **Goal matches** shows
only explicit matches for the current monitoring goal and revision, including
matches older than the most recent routine windows. Scroll down to read earlier
entries. The video stays at the top with its run status in the upper-left corner;
only the event stream below scrolls. Both views show saved frames; select a frame
to inspect it with any image-grounded highlight. Monitoring details, timings and
indexing coverage remain available through Chat and **Export**. **Show earlier** pages through all retained entries for this run, 300 at
a time. **Back to latest** resumes following new windows.

Chat records the first observation for each goal and the beginning of each
subsequent possible sighting. Use Chat to change the goal and OtterDesk to
pause or stop. An applied goal takes effect on future video windows.

The NVIDIA stream supplies caption intervals. The co-worker independently
buffers preview JPEGs and saves the one received nearest the midpoint, only
if its receipt time falls inside the interval. The thumbnail is labeled with
that time. A box is shown only when a second assessment of those exact JPEG
bytes locates a target. An observation can have no snapshot or no box.

## Search saved footage

Ask **“Did you find anyone wearing a red coat in the past hour?”** Chat searches
the current camera across runs of this Job. Search results include index coverage.
A background task indexes the caption and available
original JPEG as distinct Membrane source units. Earlier 6.0 observations are
indexed from their captions. Their images were never saved.

The blueprint's CPU operator loads Google's pinned EmbeddingGemma 2 weights
with Sentence Transformers. First use needs access to download the model or an
existing Hugging Face cache. Image, document, and query vectors share a
768-dimensional space. [Google's image encoder guide](https://ai.google.dev/gemma/docs/embeddinggemma/multimodal-embeddinggemma-with-sentence-transformers).

Membrane acknowledges the vectors before a window
counts as indexed. It ranks images by semantic similarity and captions by
hybrid search inside the requested capture interval. The existing NVIDIA
service reviews up to four candidates. Chat shows capture times, citations,
index coverage and the best reviewed snapshot when available, including uncertain or negative results with their verdict. Sampled observations
can miss activity.

## Saved state

SDK run storage is authoritative; `~/Downloads/cctv-operator` is an additional
runtime-delivered host copy. Outputs are `captions/*.json`, available `snapshots/*.jpg`, `cctv_report.json/md`,
`monitoring_state.json`, `final_artifact.json`, complete
`context_sources/outputs/*.md` accounts and `operator_activity.sqlite3`.
Published caption/report/status files use mode 0644 so the runtime's host sync
process can replicate container-root writes. Camera credentials and cleanup leases
remain outside those published accounts in Job state.

The declared Job state resource owns `realtime_vlm/captions.sqlite3`, source-scoped
history, command receipts and cleanup leases. History survives runs for the same
Job/camera. A process lock prevents two operators owning one Job. Storage stops
at 10,000 captions rather than silently deleting evidence. Review/export retention
before continuing. Reports/workspace/export show the latest 300 current-run
captions with omission counts; `get_video_history` returns up to twelve accounts,
optionally filtered by timezone-qualified capture bounds. It never reruns vision.

Other domain tools read status, completed activity and NVIDIA timings, or change
the goal. Public authenticated Job controls and operation wrapping remain SDK-owned.
Service checkpoints are bounded to 64 MiB/1,000,000 five-second
health cycles; rotate explicitly before capacity exhaustion.

## Verification

```bash
python -m pytest tests/test_cctv_realtime_*.py tests/test_mcp_cctv_operator.py -q
python -m pytest tests/test_manifest_contracts.py tests/test_catalog_native_blocks.py -q
node tests/e2e/cctv-workspace.cjs /tmp/cctv-workspace-review
git diff --check
```

The offline browser gate uses the sibling desktop checkout's declared Playwright
dependency (or `OTTERDESK_APP_ROOT`). It checks filtering, image expansion, text
escaping, scroll anchoring, empty/error states, pinned video, timeline-only scrolling
and resizing from 320 to 1440 pixels, including short windows.

To repeat the native index and retrieval gate, set `CCTV_TEST_MEMBRANE_BINARY`
to a built Membrane engine and run `tests/test_cctv_realtime_history.py` with
the operator's encoder dependencies installed. The test starts an isolated
temporary corpus. It uses real model weights and synthetic clothing images.

The opt-in Spark gate exercises the same compiled SDK hooks with an explicitly
supplied camera, real captions, preview, goal changes, saved reports, browser
resizing and resource cleanup. See [VALIDATION.md](VALIDATION.md) for results,
[SPEC.md](SPEC.md) for the contract, and
[NVIDIA's guide](https://docs.nvidia.com/vss/system-components/vision-microservices/real-time-vlm)
for the upstream service.
