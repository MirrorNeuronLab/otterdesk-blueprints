# CCTV 6.1 validation

On November 4, 2026 the native Membrane gate indexed 17 synthetic windows,
including four original JPEGs, with the pinned Google EmbeddingGemma 2
encoder. All captions described the same scene without a clothing color.
From a second run of the same Job, the past-hour red-coat question ranked the
red image first among 16 in-range windows. A separate red image from before
the interval was excluded. The in-range red image was older than the twelve
most recent captions.

The installed Docker Model Runner rejected the GGUF architecture
`gemma-embedding2` during a real embedding request. The verified write and
read paths used the blueprint's Sentence Transformers encoder and Membrane's
native source-unit index.

Chromium exercised both log filters with 310 saved windows through a prefixed
workspace URL. An older goal match remained visible, earlier pages were
reachable and snapshots decoded. Resizing between 320 and 1440 pixels produced
no horizontal overflow. The 6.1 checks used synthetic camera data. The live
NVIDIA measurements below were taken on 6.0.

## CCTV 6.0 validation — 2026-11-04

The implementation replaces the old CCTV pipeline using Spark's rt_vlm sample
and its pinned NVIDIA vss-rt-vlm 3.3.0 image. The original demo containers were
stopped as requested; their weights and caches were preserved.

## Final live deployment

- Submitted from mini through its normal Core, explicitly placed on Spark
  (`mirror_neuron@10.0.4.32`). No cluster bypass or runtime reset.
- Job: `job_co-cb158112`; execution: `cctv_operator-f9ffa3c84d`.
- Physical output run: `ngh886Me2RtJcA`; submission:
  `job_co-cb158112-def-f2a9343443c2594a`.
- Approved camera: `rtsp://10.0.4.27:8554/stream`.
- Workspace: `http://localhost:55173/jobs/job_co-cb158112/ui` on mini.
- Runtime code commit: `2601de37b`; SDK commit: `414857e2`, matching on mini and
  Spark. Subsequent validation-document changes do not alter deployed Python.

The final service remained running. Real NVIDIA captions, live preview and
public Job MCP reads authenticated by a scoped session were verified. The final
MCP smoke read four saved captions. Its short four-window sample reported
684 ms median model inference and 4,219 ms median video-window latency. A prior
26-window acceptance sample reported 750 ms median / 1,241 ms p95 inference and
4,263 ms median / 4,768 ms p95 video-window latency. These exclude model loading
and connection startup and do not measure incident-detection accuracy or
end-to-end alerts.

## Live acceptance exercised

The preceding acceptance run (`job_co-ff3edc0d`) passed forty authenticated public
Job MCP calls, including readiness, history, activity and timings. A monitoring
change and clear each completed through the SDK operation protocol and produced
new completed video windows for their goal revisions. Repeating a caller request
ID returned the same operation. Clear restored the original configured prompt.
The completed goal-change receipts required cancellation/deletion of the prior
NVIDIA request/stream before replacement. Routine captions stayed in the workspace;
Chat activity contained the first completed observation for each goal revision.

The final workspace passed Playwright through the actual UI proxy, including real
preview decoding, at least three captions, reload followed by a newly arriving
caption, export, and 1440 → 320 → 1000 → 320 → 1440 pixel resizing without page
overflow or browser errors. Wide and narrow captures were visually inspected.
The strict CSP remains enabled. Raw model text renders as text. The normal
mini workspace route also showed Running, completed captions and a decoded
preview through the cross-node proxy with no browser errors.

Acceptance artifacts on Spark are in `/tmp/cctv-v6-final-acceptance/`; public
goal-operation records from the earlier run are in
`/tmp/cctv-final-acceptance/public-mcp.json`. SDK run artifacts remain authoritative
under the shared submission/output paths above. Temporary completed test Jobs
were archived rather than deleting their evidence.

## Evidence replication

The first replication check found that the SDK atomic writer defaults to private
mode 0600, so the host sync user could not read container-root caption/report
files. Publication now explicitly uses mode 0644 for credential-free source
accounts, reports and status; the regression test checks all published files.
Previously generated public files from our acceptance runs were repaired too.

The final run's new files replicated without repair. Mini and Spark had matching
SHA-256 values for its immutable JSON caption and complete Markdown account:

- JSON: `9a753f5af3857fa56f8266f11498fd8e103e9794b30da20ef79eaf6bc507fdd7`
- Markdown: `9c24f9b7029599ad6f9396b0f27c2af6ebcbc6fda62b57d6f4ab5d88f8f0958c`

These were compared in each Core's actual shared storage while capture continued.
The cumulative report changes as new windows arrive; immutable source accounts
provide a stable comparison. Camera credentials and cleanup leases are excluded
from the published accounts.

## Shutdown and platform limitation

Pause removed the preceding run's NVIDIA container and stopped its listeners;
all fifty saved captions remained. Independent cancellation tests also removed
the owned project while retaining the external model-cache volumes.

**Resume is not qualified.** Core's current delivery-v2 invocation journal fences
replay of an interrupted long-running handler as `invocation_outcome_unconfirmed`.
The live resume attempt reproduced that guard and subsequent stale-epoch warnings.
Core's existing pause/resume E2E explicitly expects this uncertain-effect fence.
No Core code, delivery version or safety guard was changed to bypass it. Stop and
an explicitly new run are available; automatic resume needs a platform lifecycle
reconciliation contract. The final working run was launched separately.

Core can close NVIDIA before the operator's HTTP cleanup completes during a
whole-project stop. The operator records an unconfirmed cleanup lease instead of
claiming successful release. A later start must reconcile that lease with NVIDIA
before registering another stream. The native project removal itself was verified.

## Offline checks

The final focused CCTV protocol, persistence, compiled manifest, HTTP, native
listener/block lifecycle, SDK-proxy binding, MCP and catalog-block checks passed
**49 tests**. Ruff and `git diff --check` passed. Earlier focused checks including
shared input/architecture coverage passed 54 tests before the final networking
corrections; the later focused run covers the changed bindings.

The initial full catalog run had 1,295 passes, 29 skips, 50 failures and 60 errors.
CCTV's retired model/agentic assumptions and the duplicated atomic writer were
corrected afterward. Remaining failures include absent Research Assistant sources,
stale Litigation fixture versions, environment dependencies and unrelated Web Lab
changes already in progress. A final manifest/agentic gate had seven passes and
one failure caused by the absent `research_assistant/manifest.json`. The complete
catalog is not green.

## Required SDK correction and deployment settings

SDK commit `414857e2` fixes native activation of prepared inline Compose projects
without retransmitting payloads. It retains verified content-addressed source,
rejects changed/redirected/symlink contexts and preserves separate revisions.
The activation helper also uses the canonical `agents.nodes` envelope. Its 83
focused preparation/RPC tests, SDK Ruff, and wheel/sdist build passed. Spark's
existing native-SDK watchdog reloaded the matching code without a runtime reset.

The broad SDK run had 3,432 passes and 15 skips, plus six failures/four setup errors
including absent isolated-process packages and a missing mocker fixture. Installing
the required temporary test dependencies resolved the compiled-service entrypoint
failure; an unrelated native-host worker fixture still failed. This is not a clean
whole-SDK qualification.

The pinned NVIDIA image's serialized vLLM graphs failed PyTorch's metrics-context
check. The final recipe uses the supported `VLLM_DISABLE_COMPILE_CACHE=1` setting,
retaining GPU compilation/CUDA graphs and cached weights. Model warmup completed
successfully. The CPU operator uses HostLocal in Core's prepared Python environment,
private runtime-network access to NVIDIA, SDK container-proxy binding for MCP, and
Core's private interface for the separate UI proxy. These replace the incompatible
host-network/automatic-port combination found by the live gate.
