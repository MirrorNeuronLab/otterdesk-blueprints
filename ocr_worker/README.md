# OCR worker

While a batch runs, OtterDesk shows pages processed and average pages per second
in Chat's run monitor and workflow detail. Each completed document updates the
measurement; a document still in inference has no estimated page count. The
average includes model preparation and request overhead. Recovery uses the
original call timings. This requires the matching SDK with `ProcessingProgress`
on the worker and API, followed by re-preparing the co-worker.

Read PDFs, images and Office documents throughout a source folder, including its
subfolders, using NVIDIA Nemotron OCR v2. Requires a Linux NVIDIA CUDA node with
at least 48 GiB GPU memory; amd64 and arm64 (including DGX Spark) are supported.
The default sample folder contains the supplied, unmodified `stock_gs200.jpg`
Nasdaq & AMEX newspaper clipping.

From the catalog root:

```bash
mn blueprint run ./ocr_worker --set inputs.payload.input_folder=/absolute/path/documents
```

Setup accepts a **Source folder**, **Text grouping** (`paragraph`, `sentence` or
`word`) and **Output folder** (default `~/Downloads/ocr-worker`). Inputs are staged
by the platform from the submitting computer. Results are delivered to a separate
`run_<timestamp>/` folder and retained in the authoritative shared run store.
Open `~/Downloads/ocr-worker/run_<timestamp>/web/index.html` for the comparison
report, or open the co-worker's **OCR report** after the run finishes. Keep the
whole run folder together so all document and download links remain available.

The offline report places each original page beside its OCR text. Choose a
document and page, zoom the preview, show text-region boxes, or select a region
to highlight the matching text. Switch between text and region views, copy page
text, and download the captured original or extracted text/JSON. The **Files**
view lists completed, failed and skipped sources. Office previews show the
rendered pages actually sent to OCR; the original Office file remains available
to download. The report uses local assets and makes no network requests.

Supported extensions, case-insensitively:

- PDF: `.pdf`.
- Images: `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp`.
- Word: `.doc`, `.docx`, `.docm`, `.odt`, `.rtf`.
- PowerPoint: `.ppt`, `.pptx`, `.pptm`, `.pps`, `.ppsx`, `.odp`.
- Excel: `.xls`, `.xlsx`, `.xlsm`, `.xlsb`, `.ods`.

Office documents render to PDF with LibreOffice inside the worker before OCR.
Each conversion has a fresh profile with macros and active content disabled,
a three-minute deadline and bounded output. Spreadsheet results follow the
workbook's print layout; hidden sheets and content outside print areas may be
excluded. Password-protected, corrupt or unrenderable files are recorded as
failed; remaining documents continue. Unsupported extensions are listed as
skipped. Source text is data, never instructions to the co-worker.

The batch writes `ocr_result.json` and `document.md`. Each successful source also
has `documents/<relative source path>/ocr_result.json`, `text.txt` and
`document.md`, preserving subfolders and distinguishing equal filenames in
different folders. Per-document JSON retains page numbers, text regions,
normalized bounding boxes, confidence, source hash and pinned model revision.
Office entries retain both the original source hash and rendered PDF hash.
The batch explicitly distinguishes `completed`, `partial` and `failed`.

Discovery uses the shared `mirrorneuron-folder-files-skill`, also used by the
Transcription worker. Limits: 1,000 supported files, 32 MiB each, 2 GiB total,
ten directory levels, 10,000 entries and 512-byte relative paths. Symlinks,
special files and inventory-limit violations fail explicitly. PDF and rendered Office inputs allow
up to 50 pages. Images must be single-frame and at most 25 million pixels. Each
OCR response is bounded to 8 MiB, 10,000 regions and 4 MiB of text. OCR may omit or
misread text; it does not reconstruct spreadsheet cells or semantic tables.

One stock domain-operation step freezes the inventory and captures immutable
source bytes, then prepares, reads and publishes documents sequentially. The SDK
journals each model call. Recovery uses captured sources and saved responses
without repeating successful inference. Model, integrity or publication errors
stop the run; earlier document artifacts remain committed. The optional report
is published after the authoritative outputs; report or preview failures do not
invalidate extracted text. Previews are capped at 1,600 pixels per side, 8 MiB
per page and 512 MiB per batch. HTML is bounded to 32 MiB per document. Coordination messages
contain only bounded counts and artifact references.

The model recipe pins the published `homerquan/nvidia-ocr` image index for Linux
amd64 and arm64 by SHA-256. The model build uses NVIDIA's pinned multi-architecture
PyTorch base and the blueprint's bundled OCR loader, which admits both Linux CPU
architectures while requiring
CUDA. The former amd64-only image could not be pulled on Spark. First startup
compiles the CUDA extension for the actual GPU; the first inference downloads
pinned multilingual weights. Both are cached. Worker and model use the Job's
existing GPU allocation. Document bytes stay on the admitted execution node.

Model rebuild sources are in `payloads/model/`; build with `payloads/` as the
context. Publish an image index containing Linux amd64 and arm64, then pin its
digest in `execution.json`. Workers build their own Python 3.12/LibreOffice image.
Local mode resolves declared sibling skills (`MN_USE_LOCAL_SKILLS=1`); binary
mode requires a published folder-files skill satisfying `dependencies.json`.
Reprepare the co-worker after updating its blueprint so the saved definition
uses the new model image, folder contract and sample.

```bash
synapsy verify ./ocr_worker --workspace /path/to/mirror-neuron-set --compile --python /path/to/runtime/python
python -m pytest ocr_worker/tests -q
cd ocr_worker/tests
npm ci
npx playwright install chromium
PYTHON=/path/to/runtime/python npm test
```

Offline tests cover mixed recursive input, staging, conversion failures, limits,
provenance, publication, replay and optional report failure isolation. Browser
checks cover offline loading, page and file navigation, region matching, text
escaping and responsive layouts. Native GPU startup and real Office rendering
are separate live qualification checks.
