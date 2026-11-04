# CCTV 6.0 validation

The replacement uses Spark's rt_vlm sample and pinned NVIDIA vss-rt-vlm 3.3.0
image. The original sample has been stopped at the operator's request.

## Offline checks

The focused protocol, caption persistence, manifest, HTTP, native listener/block
lifecycle and MCP suite passed 36 checks. The final focused run, including shared input and
architecture checks, passed 54 checks. Ruff and `git diff --check` passed.
The first catalog-wide run completed with 1,295 passes, 29 skips, 50 failures
and 60 errors. Retired CCTV model-routing/agentic assumptions were subsequently
updated for the new service composition; the generic atomic-writer gate found
and removed a local writer in favor of the SDK's file primitives. Other failures
include absent Research Assistant sources, stale Litigation fixture versions,
test-environment dependencies and unrelated Web Lab work already in progress.
This is not a clean full-catalog qualification.

## Required SDK correction

SDK commit `414857e2` fixes activation of inline Compose projects without
retransmitting source payloads. It retains and verifies content-addressed native
source, rejects changed/redirected/symlink contexts and preserves separate revisions.
The normal activation helper also now uses the canonical agents.nodes envelope.
It passed 83 focused preparation/RPC tests, whole-SDK Ruff and a wheel/sdist build.
The broad SDK run had 3,432 passes and 15 skips; six failures/four setup errors
included missing isolated-process packages and the missing mocker fixture.
Mini and Spark use the same SDK commit, and Spark's existing native SDK watchdog
has reloaded it. No runtime reset or data deletion was performed.

## Live acceptance

Approved source: `rtsp://10.0.4.27:8554/stream`. The final live gate remains in
progress. An initial native run exposed the SDK inline-context activation bug
before NVIDIA startup. Its retained run receipt is `run_co-86e40e5a` on Spark.
No real caption result is claimed from that attempt. The first federated CLI
start reported local exclusive-resource contention; starting its prepared Job
through Spark's normal local Core reserved the Spark GPU successfully.

Live acceptance must verify real consecutive captions, preview, goal replacement,
saved reports/history, browser resizing and request/stream cleanup. Timing figures
will distinguish NVIDIA inference/window latency from model loading and connection
startup. No site accuracy or safety qualification is implied.
