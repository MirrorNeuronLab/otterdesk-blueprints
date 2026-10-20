# CT reader

The source folder is `ct_reader`; the stable blueprint ID remains `ct_scan_reader`.

**Research and education only. Not for real diagnosis, treatment, triage, or clinical decisions.** Experimental model output may be incorrect. This co-worker is not a medical device.

Upload a de-identified chest or abdominal CT with the **+** button at the bottom of Chat, then choose the anatomy present in the scan. Work starts when the required inputs are ready. The original scan can be previewed in Chat with NiiVue; the model interprets its own anatomy-aware crop, so the preview is not an overlay or proof of complete coverage. The upload message immediately includes three saved middle-slice images in
Chat's existing media card. Their orientation is unlabeled; they are previews of
the original volume, not the model's crop. The complete interactive viewer is
still available from the composer attachment. No example patient data is bundled.

One NVIDIA CUDA GPU with at least **48 GiB (49,152 MiB)** device memory is mandatory. CPU, Apple GPU, and AMD execution are not supported. Separate GPUs cannot pool their memory to meet this requirement. Spark's NVIDIA GB10 is a supported deployment target, subject to available memory at admission. Scans must contain Hounsfield-unit intensities. Inputs are single-channel 3D NIfTI-1 `.nii` or `.nii.gz`, at most 64 MiB on disk and 256 MiB expanded.

## Docker delivery

The implementation is based on `/home/homer/Sandbox/ct/inference.py` on Spark and [NVIDIA NV-Reason-CT](https://github.com/NVIDIA-Medtech/NV-Reason-CT). Model weights and custom processor code are pinned to Hugging Face revision `386b93e034983f6c1fc841a43833a1b6a0cd9c13`. The model image uses the tested Spark PyTorch CUDA 13 / Transformers versions. No Flask development server or fabricated report is used.

The model image is published as a public image on Docker Hub for
Linux ARM64 (including Spark) and AMD64 NVIDIA nodes:

```text
docker.io/homerquan/nv-reason-ct@sha256:b5563c5c26d41d29d7f324af514044f6b8ab9cfe3b099491d364ec43eef77203
```

The release tag is `docker.io/homerquan/nv-reason-ct:0.1.1`. The blueprint pins the immutable
multi-platform digest, so both architectures use the reviewed release. Pulls
require no registry account or credentials. The image contains model-serving
code and dependencies; the pinned Hugging Face model weights are downloaded
into the runtime-owned cache on first use. No CT data is included in the image.

As in `mn-blueprints/demo_air_gapped`, the model declaration belongs to this blueprint.
Here the source weights come from [Hugging Face NV-Reason-CT](https://huggingface.co/nvidia/NV-Reason-CT)
at the pinned revision rather than bundled model files. The existing SDK uses the
`docker_model_runner` preparation provider with `source: docker`,
`backend: docker`, and `protocol: http_json`; this image serves a native CT API.

The shared SDK `runtime_model_json_request` selects and prepares the owned
container, then sends native CT JSON directly to `/v1/ct`. The runtime owns
cold starts, readiness, admission leases, run/attempt retention, unloading after
the final reference, and cache reuse. The blueprint contains no transport or
container lifecycle implementation. CT inference bypasses LiteLLM; NIfTI bytes
and anatomy parameters use NVIDIA's custom 3D interface.

**Do not add NV-Reason-CT to the SDK model catalog.** The native and worker SDK
must support the shared Docker `http_json` protocol. Normal hiring builds the
CPU worker and pulls the public model image; weights download from Hugging Face
at the pinned revision on the selected NVIDIA GPU node.

For local image development:

```bash
docker build -t mirror-neuron/nv-reason-ct:0.1.1 ct_reader/payloads/model
```

The CPU workflow worker is separately built through the standard `python_docker` contract. CT inference runs in the GPU model container via the SDK's managed model request; neither worker mounts the Docker socket or arbitrary host directories. Model downloads need Hugging Face access on first use. The model cache is an owned Docker volume.

## Data and results

The runtime stages the selected scan to the execution node. CT bytes are sent only to the selected runtime model endpoint, never to Hugging Face or a public preview site. The desktop preview loads bytes locally in its renderer. Consider all connected runtime nodes part of the data boundary; de-identify scans before upload. No raw volumes, prompts, or reports are logged.

`final_artifact.json` and `report.md` are saved under the SDK-provided run output. They include experimental output, a research-only notice, source SHA-256, selected anatomy, model revision, and explicit limitations. The `conversation_result_text:report.md` capability tells OtterDesk to display the
complete saved report directly as text in Chat once the run completes, including
its research notice and limitations. No open action or additional inference is
required. Results are private run data; no clinical accuracy or calibrated
confidence is asserted. Rerunning with a different CT or research question is an explicit new run, not hidden conversation inference.

```bash
mn blueprint run --folder ./ct_reader \
  --set inputs.payload.ct_file=/absolute/path/to/deidentified.nii.gz \
  --set inputs.payload.region=chest
python -m pytest tests/test_ct_reader.py -q
```

Chat's introduction asks for the upload. The exact `conversation_file_upload:nifti` product capability opts this blueprint into the desktop upload control; exactly one non-secret `local_path` file field with `role: input` must be declared. Other co-workers remain unchanged.

## Verification

Version 2 uses the optional SDK `blueprint-blocks` component for the native
computation step. The blueprint keeps CT validation, the pinned model and report
composition. Shared code owns worker binding, bounded artifact messages,
invocation replay and uncertain-effect fencing. The volume is snapshotted before
dispatch; a retry can reconcile a completed saved report without another model
request. An interrupted request with no durable result remains uncertain and
requires an explicit new run or reconciliation. Install the matching
SDK/common/blocks family from `1.3.61.dev25` onward. The block migration is covered
by offline tests; the historical live checks below predate this migration.

On 2026-10-14, `mirror-neuron/nv-reason-ct:0.1.1` built successfully on Spark
(Linux ARM64, NVIDIA GB10). An isolated container loaded the pinned model from
Spark's existing cache mounted read-only, accepted NVIDIA's public
`example_1.nii.gz` through `/v1/ct`, and returned a nonempty 1,663-character
research response. The test container was removed afterward; no runtime
configuration or services were changed. Manifest compilation, special-model
validation, report idempotency, input limits, and API tests also passed.

The desktop Electron gate verified upload, local WebGL preview, persisted input,
wide-to-narrow resizing at 1,180 pixels, and starts only after all required answers are supplied. This is a
functional smoke test, not clinical validation. Anonymous registry access and both published image platforms were verified.
An end-to-end runtime hire/run remains a release gate; this task did not
change or reinstall the runtime.

The shared runtime integration was also exercised through the canonical API on
Spark: the existing CT job accepted a new run, the SDK selected its native Docker
HTTP endpoint, and the run completed with a research-only report from the pinned
model revision. Terminal cleanup stopped the model container while retaining its
owned cache. This checks runtime orchestration and lifecycle, not clinical accuracy.


## Result-explanation knowledge

The existing enabled RAG and Job response service consume Markdown under
`knowledge/`. The bundled guides explain report structure, common CT terms,
uncertainty, preview/model limitations, and saved provenance. They include source
links checked on 2026-10-14 and clearly labeled fictional examples. The co-worker
can explain the saved report's wording; this knowledge does not authorize a new
scan interpretation, diagnosis, treatment, or follow-up schedule.

## Standard MCP supervision

This package requires `mn.mcp.supervision.v1`. The SDK implements the shared manual, capabilities, context, results, activity, lifecycle, and operation tools. `knowledge/user_manual.md` is bundled with the prepared Job. Domain tools and their native JSON input/output schemas are declared once in `extensions/mcp.json`; response agents derive their bindings from it. All tool results use `mn.mcp.tool_result.v1`. Mutations require a request ID, and asynchronous work is observed through `get_operation_status`. Upgrade the installed SDK/API/desktop together and update idle Job definitions before using this contract.
