# CT preview, model limits, and saved evidence

Research and education only. Not for real diagnosis, treatment, triage, or clinical decisions.

## What the model receives

CT reader uses the pinned NVIDIA NV-Reason-CT model for chest or abdominal research reports. The source volume must contain CT intensities in Hounsfield units. NVIDIA's processor selects an anatomy-aware crop, resamples to 2 mm spacing, and uses a 192 × 192 × 192 volume. Selection of chest or abdomen must match the uploaded data. Cropping can omit structures; a chest result does not establish findings throughout an entire body scan.

Generated reasoning is reviewable text. It is not guaranteed to expose the model's internal computations, and it is not independent verification of the answer. Clinical correctness and patient-specific confidence are not established by this co-worker.

## What Chat shows

The upload message contains three central voxel-plane images of the original volume. Their orientation is unlabeled. They use a fixed −1000 to 1000 HU display window. The composer attachment provides an interactive NiiVue preview with lung, soft tissue, and bone display windows. These are display settings, not additional model analyses.

The preview shows the original input, not the model's selected crop, a lesion overlay, a segmentation, or a measurement tool. A structure's absence from a middle slice does not prove that it is absent from the scan. Different window settings can change its visibility without changing the underlying volume.

## What the saved report contains

`report.md` is the displayed experimental text. `final_artifact.json` records the research notice, input SHA-256, selected anatomy, research question, model identifier and revision, answer, and limitations.

The input hash identifies file bytes; it is not a patient identity or a clinical quality check. The model revision identifies the reviewed model source; it does not certify the result. Preserve this provenance when explaining which run produced a report.

## Questions the co-worker can answer

- Why does the preview differ from the report's description?
- What does changing a display window do?
- Was this a chest or abdomen run?
- Which saved limitations apply to this result?
- What does the recorded model revision or input hash mean?

Use saved run evidence to answer run-specific questions. Say when it is unavailable. Explaining a completed report does not reread the scan or launch another inference. A different scan, anatomy choice, or research question requires an explicit new run with the configured inputs.

## Sources

Sources checked on 2026-10-14.

- [NVIDIA's pinned model card: anatomy cropping and model limitations](https://huggingface.co/nvidia/NV-Reason-CT/blob/386b93e034983f6c1fc841a43833a1b6a0cd9c13/README.md).
- [CT reader specification](../SPEC.md) and [report writer](../payloads/domain/reporting.py) describe the product implementation and saved evidence.
