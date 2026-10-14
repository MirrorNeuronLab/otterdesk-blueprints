# CT research reader specification

## Mission and boundary

Explore NVIDIA NV-Reason-CT output for research and education. **Not for real diagnosis, treatment, triage, or clinical decisions.** Never infer clinical validity from an experimental report or visual preview.

## Inputs and behavior

Ask the supervisor to upload a de-identified `.nii` or `.nii.gz` CT in conversation and select chest or abdomen. Accept single-channel, finite-intensity, three-dimensional NIfTI-1 volumes with Hounsfield units. Bound compressed inputs to 64 MiB and expanded volumes to 256 MiB. Keep the optional research question under 2,000 characters. Preview the original volume locally through NiiVue. Explicit Start now launches one bounded inference; selecting an input alone never starts work.

Require one NVIDIA CUDA GPU with at least 48 GiB device memory. Declare NV-Reason-CT using the existing blueprint special-model Docker specification, never the SDK catalog. Keep runtime, SDK, CLI, and global model defaults unchanged.

## Outputs and evaluation

Save an experimental report and source/model provenance before returning bounded artifact references. Reject malformed volumes, unsupported anatomy, missing GPU capacity, empty answers, model failures, and outputs lacking the research-only marker. Duplicate invocation returns the same saved result and does not re-run inference. A changed input in the same invocation fails.

Validate manifest compilation, strict GPU constraints, file limits and gzip behavior, model dispatch, idempotent durable output, and research-only labeling with deterministic tests. A live Docker/GPU smoke test is a deployment gate, not a unit-test requirement. No clinical performance claim is part of acceptance.

## Limits

The model uses an anatomy-aware 192³ crop at 2 mm resolution. The original-volume preview does not show that exact crop or localize findings. Reports may omit anatomy, hallucinate findings, or be wrong. This version supports one scan per run and no DICOM input, 4D time series, patient triage, external patient-data upload, clinical diagnosis, treatment recommendation, or calibrated confidence.
