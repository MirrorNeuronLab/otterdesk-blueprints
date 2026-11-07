# NVIDIA OCR user manual

Upload a PNG, JPEG, TIFF, BMP, WebP or PDF (at most 32 MiB and 50 pages), or select
the bundled synthetic sample. Start the run through the normal Job controls.
The coworker extracts all pages and publishes `ocr_result.json`, `text.txt` and
`document.md`. JSON retains page numbers, normalized bounding boxes, confidence
scores, source SHA-256, pinned model revision and empty-page warnings.

Requires Linux amd64, Docker with NVIDIA GPU access and one GPU with at least
48 GiB memory. The first run builds the CUDA image and downloads multilingual
Nemotron OCR v2 weights; later runs reuse the runtime cache. Job preparation and
Chat do not download OCR weights. Inference stays on the admitted node.

OCR can omit or misread text; review critical fields against the source. There is
no claim of perfect table reconstruction. Chat questions never start a run.
Use `get_run_status` and `get_run_results` to inspect observed completion.
