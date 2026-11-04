# CCTV co-worker

Version 6.0.0 is a complete replacement based on the working sample at
`spark:/home/homer/Sandbox/rt_vlm`. NVIDIA `vss-rt-vlm` 3.3.0 owns DeepStream
video decoding, window sampling and Cosmos3 Edge inference. The co-worker saves
completed streaming captions and supplies a separate, read-only live preview.
The previous detector, CUDA relay, semantic decision model and visual-history
pipeline are removed. Old private databases are not migrated.

## Start

Enter an approved RTSP/RTSPS camera through OtterDesk's secure **Video stream URL**
field, and optionally specify a visible monitoring goal. No camera is included.
Credentials remain server-side; never paste them into Chat or shell commands.

```bash
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.32 --web-ui \
  --set video_source.uri=rtsp://camera.example/approved-stream
```

Refresh an idle prepared Job to adopt this major version. Existing runs retain
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

The browser restores saved observations and polls every two seconds. It has no
action endpoints. Use Chat to change the goal and OtterDesk to pause/stop. A goal
change releases the prior request before opening the next one and retains the
transcript. An applied receipt is separate from a new analyzed window. The first
completed caption for each goal revision appears in Chat; routine windows stay
in the workspace. Clearing restores the configured goal.

NVIDIA does not return the exact selected images through this protocol. The live
preview and snapshot are never labeled analyzed evidence. Captions are fallible
model descriptions, not verified event verdicts, calibrated confidence, exhaustive
coverage, unique-person counts, compliance assessments or safety guarantees.
Review original video before acting. No external alerts or physical actions occur.

## Saved state

SDK run storage is authoritative; `~/Downloads/cctv-operator` is an additional
runtime-delivered host copy. Outputs are `captions/*.json`, `cctv_report.json/md`,
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
No separate vision-model recipe, secondary semantic model or CPU inference
fallback exists. Service checkpoints are bounded to 64 MiB/1,000,000 five-second
health cycles; rotate explicitly before capacity exhaustion.

## Verification

```bash
python -m pytest tests/test_cctv_realtime_*.py tests/test_mcp_cctv_operator.py -q
python -m pytest tests/test_manifest_contracts.py tests/test_catalog_native_blocks.py -q
git diff --check
```

The opt-in Spark gate exercises the same compiled SDK hooks with an explicitly
supplied camera, real captions, preview, goal changes, saved reports, browser
resizing and resource cleanup. See [VALIDATION.md](VALIDATION.md) for results,
[SPEC.md](SPEC.md) for the contract, and
[NVIDIA's guide](https://docs.nvidia.com/vss/system-components/vision-microservices/real-time-vlm)
for the upstream service.
