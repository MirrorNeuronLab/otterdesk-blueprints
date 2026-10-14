# CT research reader

**Research and education only. Not for real diagnosis, treatment, triage, or clinical decisions.** Experimental model output may be incorrect. This co-worker is not a medical device.

Upload a de-identified chest or abdominal CT in Chat using **Upload CT**, choose the anatomy present in the scan, save setup, then choose **Start now**. The original scan can be previewed in Chat with NiiVue; the model interprets its own anatomy-aware crop, so the preview is not an overlay or proof of complete coverage. No example patient data is bundled.

One NVIDIA CUDA GPU with at least **48 GiB (49,152 MiB)** device memory is mandatory. CPU, Apple GPU, and AMD execution are not supported. Separate GPUs cannot pool their memory to meet this requirement. Spark's NVIDIA GB10 is a supported deployment target, subject to available memory at admission. Scans must contain Hounsfield-unit intensities. Inputs are single-channel 3D NIfTI-1 `.nii` or `.nii.gz`, at most 64 MiB on disk and 256 MiB expanded.

## Docker delivery

The implementation is based on `/home/homer/Sandbox/ct/inference.py` on Spark and [NVIDIA NV-Reason-CT](https://github.com/NVIDIA-Medtech/NV-Reason-CT). Model weights and custom processor code are pinned to Hugging Face revision `386b93e034983f6c1fc841a43833a1b6a0cd9c13`. The model image uses the tested Spark PyTorch CUDA 13 / Transformers versions. No Flask development server or fabricated report is used.

The model image is published as a public image on Docker Hub for
Linux ARM64 (including Spark) and AMD64 NVIDIA nodes:

```text
docker.io/homerquan/nv-reason-ct@sha256:981c8278e77d55524490800c7528f0fbae93e06d6aab52f9c180c614cd6946a7
```

The release tag is `docker.io/homerquan/nv-reason-ct:0.1.0`. The blueprint pins the immutable
multi-platform digest, so both architectures use the reviewed release. Pulls
require no registry account or credentials. The image contains model-serving
code and dependencies; the pinned Hugging Face model weights are downloaded
into the runtime-owned cache on first use. No CT data is included in the image.

The existing runtime `customize_mode` + Docker `model_spec` contract downloads
and owns this model container, including its cache and GPU placement.
**Do not add NV-Reason-CT to the SDK model catalog. No runtime changes or
reinstall are required by this blueprint.** No manual image build is needed
for normal hiring.

For local image development:

```bash
docker build -t mirror-neuron/nv-reason-ct:0.1.0 ct_scan_reader/payloads/model
```

The CPU workflow worker is separately built through the standard `python_docker` contract. CT inference runs in the GPU model container via the SDK's managed model request; neither worker mounts the Docker socket or arbitrary host directories. Model downloads need Hugging Face access on first use. The model cache is an owned Docker volume.

## Data and results

The runtime stages the selected scan to the execution node. CT bytes are sent only to the selected runtime model endpoint, never to Hugging Face or a public preview site. The desktop preview loads bytes locally in its renderer. Consider all connected runtime nodes part of the data boundary; de-identify scans before upload. No raw volumes, prompts, or reports are logged.

`final_artifact.json` and `report.md` are saved under the SDK-provided run output. They include experimental output, a research-only notice, source SHA-256, selected anatomy, model revision, and explicit limitations. Results are private run data; no clinical accuracy or calibrated confidence is asserted. Rerunning with a different CT or research question is an explicit new run, not hidden conversation inference.

```bash
mn blueprint run --folder ./ct_scan_reader \
  --set inputs.payload.ct_file=/absolute/path/to/deidentified.nii.gz \
  --set inputs.payload.region=chest
python -m pytest tests/test_ct_scan_reader.py -q
```

Chat's introduction asks for the upload. The exact `conversation_file_upload:nifti` product capability opts this blueprint into the desktop upload control; exactly one non-secret `local_path` file field with `role: input` must be declared. Other co-workers remain unchanged.

## Verification

On 2026-10-14, `mirror-neuron/nv-reason-ct:0.1.0` built successfully on Spark
(Linux ARM64, NVIDIA GB10). An isolated container loaded the pinned model from
Spark's existing cache mounted read-only, accepted NVIDIA's public
`example_1.nii.gz` through `/v1/ct`, and returned a nonempty 1,663-character
research response. The test container was removed afterward; no runtime
configuration or services were changed. Manifest compilation, special-model
validation, report idempotency, input limits, and API tests also passed.

The desktop Electron gate verified upload, local WebGL preview, persisted input,
wide-to-narrow resizing at 1,180 pixels, and no automatic run. This is a
functional smoke test, not clinical validation. Anonymous registry access and both published image platforms were verified.
An end-to-end runtime hire/run remains a release gate; this task did not
change or reinstall the runtime.
