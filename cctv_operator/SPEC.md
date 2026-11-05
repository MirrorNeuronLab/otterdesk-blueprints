# CCTV co-worker 6.1.0

## Product and compatibility

One approved RTSP/RTSPS camera per Job. Describe visible activity in sampled
video windows, preserve timestamps and source references, show a separate live
preview, accept supervised monitoring goals and save observations across runs.
This replaces the previous implementation using Spark's rt_vlm sample. Previous
graphs, detector policies, model recipes and private databases are retired.

## Execution

The required NVIDIA vss-rt-vlm 3.3.0 container owns analysis decode/sampling and
Cosmos3 Edge inference. Pin the sample's ARM64/SBSA digest. Defaults: four-second
windows, eight frames, 608×320 input, 192 tokens, temperature 0.2, no reasoning
or audio. Discover the model from /v1/models after /v1/ready; an empty model list
cannot establish readiness. No person gate, semantic decision model or alternate
inference provider exists.

Core owns native Compose preparation, selected-node placement, health and project
cleanup. Reserve loopback port 8019 and hard-require NVIDIA CUDA with 49,152 MB
GPU/unified memory. One VSS stack per node; pre-provisioned external model-cache
volumes persist independently of Compose cleanup. The Python 3.12 HostLocal
operator connects through the private runtime network; native Compose health
checks use the host-loopback endpoint. Internal MCP/workspace listeners use
Core-assigned ports. Recompile vLLM graphs at startup because the pinned image's
serialized compilation cache fails PyTorch's metrics-context check on Spark;
model weights remain cached and GPU inference stays compiled.
SDK monitored-service hooks supervise the operator's
listeners, streaming task, preview and publication. Startup is bounded to 1,200
seconds; health checkpoints to 64 MiB/1,000,000 cycles, five seconds apart.

Current platform limitation: delivery-v2 pause interrupts the long-running native
invocations. Core fences their replay as `invocation_outcome_unconfirmed`; automatic
resume is not supported by this qualification. Preserve that guard. Stop releases
the project; an explicitly new run can continue using the Job's saved captions.

Register the stream, consume /v1/generate_captions SSE, cancel its request, then
delete the stream using its request ID when available. Only 409 cleanup receives
five bounded retries. One caption request is active per operator. Stop and goal
changes await registration/cancellation/cleanup before replacement. Retain unknown
registration outcomes and failed cleanup in Job state; block further registration
until reconciled. Inference failure is explicit, never silently retried.
The pinned NVIDIA AssetManager reports an absent resource with HTTP 400,
`BadParameter`, and an exact resource-specific message. Its `No such resource
<stream-id>` and `<stream-id> already deleted because of age out policy` receipts
prove a saved stream is gone after restart/expiry and complete cleanup. Other
400 responses, wrong identities, transport failures, and unknown registration
outcomes retain the ownership fence.

## Evidence and persistence

Validate camera input without echoing credentials. URI data never enters public
state, captions, reports or Chat. Bind storage to Job identity and history to a
credential-free camera locator hash. A process lock enforces one Job owner.

Require bounded nonempty captions, chronological timezone-qualified capture
bounds, valid optional finite non-negative latency and complete output. Reject
private reasoning. Deduplicate session/window identities. Save complete source
accounts before final SDK activity publication. Model errors, unexpected EOF,
invalid records and cleanup failures remain visible. Preview health is separate.

Save immutable caption JSON, complete source Markdown, cumulative JSON/Markdown
reports, monitoring state and the standard final artifact. Reports/export/workspace
are bounded to 300 current-run accounts with omissions. Source-scoped Job history
stops at its explicit 10,000-account capacity without automatic deletion. A chronological history read returns up to twelve accounts and omissions. The separate
question tool searches acknowledged Membrane text and image units across this Job and
camera, constrained by the requested capture interval. It resolves relative intervals
once at dispatch and preserves them through polling and retries. Old caption-only
accounts remain searchable. Report pending indexing and sampled coverage.

NVIDIA's caption protocol does not return selected image evidence. Preview and
window snapshots use the independently decoded preview. Save only a JPEG received inside
the window. A localization must come from a separate review of that exact JPEG. Captions remain
fallible sampled descriptions. Do not infer exhaustive coverage, unique people,
identity, compliance, calibrated confidence, verified incidents or safety. No
external messaging or physical action occurs. A human reviews original video.

## Supervision

Use standard Job MCP supervision. Domain tools read status, final activity, saved
history and retained NVIDIA timing, or set the monitoring prompt. Durable caller
IDs reject conflicting reuse. Preserve arbitrary visible subject/condition/negation.
An applied prompt is separate from a later completed window; clear restores the
configured goal. Retrospective questions never change monitoring. Chat shows the first completed window per goal revision and the start of each
possible sighting. The read-only workspace provides newest-first all-message and
current-goal timelines with inspectable saved images in both views. Keep the video
at the top with run status over its upper-left corner; only the event stream below
scrolls. Omit the camera heading, monitoring prompt and routine diagnostics from
the page. Camera identity remains accessible through the preview label and tooltip;
monitoring details remain available through Chat and export. History answers include a reviewed still when available, preserving its verdict and any image-grounded box. A positive structured verdict is required for the goal view. SDK/Core retain lifecycle controls, public authentication and envelopes.

The read-only workspace polls saved state every two seconds and restores after
reload. Render model text as text. Keep credentials, action endpoints and raw
NVIDIA APIs out of the browser. Preserve capture/receipt time distinctions and
prevent horizontal overflow through narrow/wide resizing.

## Acceptance

Offline tests cover real compiled bindings, protocol parsing, source isolation,
persistence, cancellation/cleanup fencing, goal receipts, read-only HTTP, text
escaping, layout and native lifecycle. Live acceptance needs consecutive NVIDIA
captions on the approved camera, goal replacement, preview, durable history and
proven release of owned requests/streams. Prior sample results are not acceptance
for this implementation. Measure model/window timing separately from loading,
startup and end-to-end incident latency. Site accuracy needs labeled footage.
