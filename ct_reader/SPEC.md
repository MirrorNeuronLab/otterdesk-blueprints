# CT reader specification

## Mission and boundary

Explore NVIDIA NV-Reason-CT output for research and education. **Not for real diagnosis, treatment, triage, or clinical decisions.** Never infer clinical validity from an experimental report or visual preview.

## Inputs and behavior

Ask the supervisor to upload a de-identified `.nii` or `.nii.gz` CT in conversation and select chest or abdomen. Accept single-channel, finite-intensity, three-dimensional NIfTI-1 volumes with Hounsfield units. Bound compressed inputs to 64 MiB and expanded volumes to 256 MiB. Keep the optional research question under 2,000 characters. Show three local middle-slice images in the upload message's existing Chat media
card, retaining them in saved history. Mark preview orientation as unlabeled and
preserve research-only notices. Preview the original volume interactively through
NiiVue from the composer attachment. Supplying the final required setup answer launches one bounded inference without a separate save or start button. An incomplete upload never starts work.

Require one NVIDIA CUDA GPU with at least 48 GiB device memory. Declare NV-Reason-CT as a blueprint-owned Docker `model_spec` with the shared `http_json` protocol, never in the SDK catalog. Use the native CT API directly on the selected Docker model node, bypassing LiteLLM inference. Download pinned weights from Hugging Face on first use. Use the shared runtime lifecycle for preparation, readiness, admission, run retention, unloading and cache reuse; the blueprint contains no transport or container-control patch. Keep global model defaults unchanged.

## Outputs and evaluation

`mn.blocks.native_computation@1` supplies the standard specialist worker. Domain
hooks prepare the bounded volume reference, validate the research-only response
and compose the report. The shared SDK capability dispatches the native model
request and reconciles a durably saved response. The block
binds source/config/code identities and inputs to its invocation, verifies
artifact hashes and fences uncertain native requests. It does not pass volume
bytes through coordination messages. The `read_ct_volume` logical step and
public report files retain their contracts; generated worker identity changes
in version 2. Version 3 removes the blueprint-owned native-task adapter. Removed local step/agent/runtime wrappers have no second execution
path. The block call budget is one native dispatch and its deadline is 900s;
the existing native transport timeout remains 600s with zero retries.

Save an experimental report and source/model provenance before returning bounded
artifact references. Declare `conversation_result_text:report.md` so OtterDesk
displays the complete saved report as text in Chat after completion, with its
notice and limitations and no separate open action. Reject malformed volumes, unsupported anatomy, missing GPU capacity, empty answers, model failures, and outputs lacking the research-only marker. Duplicate invocation returns the same saved result and does not re-run inference. A changed input in the same invocation fails.

Validate manifest compilation, strict GPU constraints, file limits and gzip behavior, model dispatch, idempotent durable output, and research-only labeling with deterministic tests. A live Docker/GPU smoke test is a deployment gate, not a unit-test requirement. No clinical performance claim is part of acceptance.

## Limits

The model uses an anatomy-aware 192³ crop at 2 mm resolution. The original-volume preview does not show that exact crop or localize findings. Reports may omit anatomy, hallucinate findings, or be wrong. This version supports one scan per run and no DICOM input, 4D time series, patient triage, external patient-data upload, clinical diagnosis, treatment recommendation, or calibrated confidence.


## Educational result explanations

Bundle concise Markdown references in `knowledge/` through the existing enabled
RAG and Job response service. Explain report sections and terms, preserve
negation and uncertainty, and distinguish the saved model text from general
background. Include traceable primary-source links, model-revision context, and
labeled fictional examples. Do not fabricate missing findings or replace
qualified clinical review. Explaining a saved result does not launch inference.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.

## Block composition (3.0.0)

Use the stock native capability with `config.model: ct`. Native requests contain
only a relative API path and payload; the committed volume is bound with explicit
base64 encoding and materialized only for dispatch. The block freezes that request
before the effect and preserves the raw native response before publication.
Publication retries reuse both, including if the original local file changes.
Unknown dispatch outcomes remain blocked, and completed replay verifies published
artifact bytes. SDK/blocks >=1.4.1.dev14 with matching native capability support
are required. The existing Docker worker, NVIDIA requirement, managed model
lifecycle, pinned image and scientific limitations remain authoritative.

The native block declares the required research-only marker, nonempty answer
and model revision in `config.response_schema`. The SDK checks that contract
without changing live request bodies. Explicit fake mode uses a structural
example stating that no scan findings were evaluated. Final JSON and Markdown
are registered as verified runtime downloads through the SDK publication adapter.
