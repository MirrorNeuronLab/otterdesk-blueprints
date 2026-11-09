# OCR worker specification

After each validated, published document, report its measured page count through
the SDK's generic `ProcessingProgress` hook (`page`). The SDK's original model
response receipt supplies duration, including setup/request overhead, and sample
time even on recovery. Exclude failed inputs and never estimate pages in an
unfinished request. Measurements contain no filenames or source text and do not
change inference, resource allocation, publication or workflow completion.

Accept an authorized source folder and recursively process its PDF, supported
single-frame image, Word, PowerPoint and Excel/OpenDocument files. Use
`nvidia/nemotron-ocr-v2` multilingual at revision
`0e83e83f17943524b90afa6c0fd82ac2bc1a40ca`. The stock domain-operation block owns
bounded orchestration through public SDK hooks; the shared folder-files skill
owns discovery. Document selection, Office preparation and report policy remain
in the blueprint.

The source inventory is deterministic and frozen before inference. Capture every
selected file durably; repeated execution uses that capture even if the original
folder changes. Preserve relative names and distinguish identical basenames in
different folders. Treat document contents as data only.

For each successful document, commit and publish JSON, plain text and Markdown
under `documents/<relative source path>/`. JSON binds every page to the OCR
input SHA-256 and model revision and preserves ordered regions, normalized boxes,
confidence and explicit empty-page warnings. Office documents are rendered with
headless LibreOffice in the worker and retain both original and rendered hashes.
Use isolated temporary profiles, disabled macros/active content/link updates,
fixed argument arrays and a cancellable 180-second conversion deadline.

Publish authoritative `ocr_result.json` (`mn.nvidia_ocr.batch.v1`) and a Markdown
batch summary. Report completed, failed and unsupported/skipped sources and
counts. Invalid or unrenderable source files do not prevent other files from
being processed. An all-invalid batch publishes its failure summary and fails the run; a mixed batch is
`partial`. Inventory violations, missing worker dependencies, runtime/model
failures, malformed/mismatched model responses and authoritative publication failures abort
execution. Do not fabricate missing results. Saved inference is never repeated
on recovery, including after publication failure. No document text enters
coordination messages or activity logs.

Limits: 1,000 selected files; 32 MiB per original or rendered file; 2 GiB captured
source bytes; depth ten; 10,000 entries; 512-byte relative paths; no symlinks or
special files. PDFs and Office renderings allow 1–50 pages. Images are single-frame
and at most 25 million pixels. Model PDF rasterization bounds each rendered page.
Per-document model output allows 8 MiB, 10,000 regions and 4 MiB text. Inference
has a 900-second deadline per document; the batch has a 24-hour deadline.
Unsupported extensions are accounted for, not presented as processed.

Requirements: Linux amd64 or arm64, NVIDIA CUDA, one GPU with at least 49,152 MiB
memory, 8 GiB CPU RAM, four CPU cores and 40 GiB disk. Reuse the Job allocation for
worker and model. Pin a model image index supporting both CPU platforms. The
bundled loader admits ARM64/Spark; native extension caches distinguish CPU and
GPU architectures. Weights are loaded lazily on the first inference. Model and
worker dependencies are declared once in their owning role documents.

The default `@/examples/sample_inputs` folder contains the supervisor's unchanged
`stock_gs200.jpg`. Setup and default configuration reference that same folder.
Default additional host delivery is `~/Downloads/ocr-worker/run_<timestamp>/`.
After authoritative publication, produce an optional static `web/index.html`
comparison report and `web_ui.json` handle through the SDK. The report uses the
shared web-report shell with local assets and no service or network dependency.
Show captured originals beside committed OCR text with document/page selection,
zoom, corresponding text regions, copy/download actions and explicit failed,
skipped and empty results. Render PDF/Office page previews from the exact hashed
bytes sent to OCR. Download originals from the immutable source capture. Source
names and text remain escaped data; never execute or embed Office/PDF originals.
Bound previews to 1,600 pixels on the longest edge, 8 MiB per page and 512 MiB per
batch; bound each HTML page to 32 MiB. A missing preview retains text and original
downloads. Optional report/handle failures cannot invalidate domain results or
block successful run completion. Preserve cancellation checks. No desktop
application, SDK or existing shared skill changes are required.

Acceptance: compiled offline tests verify recursive staging, all supported format
classes, exclusions/failures, source and rendered hashes, durable per-file results
and replay. Native Spark validation must start the pinned model and recover the
newspaper heading. Live Office checks must render Word, PowerPoint and Excel
sources in the worker image. OCR quality and Office print-layout omissions remain
visible limitations; this is not semantic table or spreadsheet extraction.
