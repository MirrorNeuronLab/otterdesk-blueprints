# NVIDIA OCR user manual

Select a **Source folder**, or use the sample folder containing the Nasdaq & AMEX
newspaper image. Start the co-worker to read PDFs, PNG/JPEG/TIFF/BMP/WebP images,
Word, PowerPoint, Excel and OpenDocument files in that folder and its subfolders.
The folder may contain up to 1,000 supported files, 32 MiB each and 2 GiB total.
PDFs and rendered Office documents allow up to 50 pages. Images must be single-frame.

Each run saves a batch summary plus per-file text, Markdown and page-region JSON.
Subfolder names are preserved under `documents/`. The default output folder is
`~/Downloads/nvidia-ocr`, with a separate `run_<timestamp>/` folder for each run.
Open `web/index.html` inside that run folder, or the co-worker's **OCR report**,
to compare original pages and extracted text side by side. Select a document and
page; zoom the preview or enable **Show text regions** and click a region to find
its text. **View** switches between full page text and individual regions. Use
**Copy page text**, **Download original**, or **Actions** to save extracted text
or page data. **Files** lists completed, failed and unsupported documents. The
report works offline; keep the whole run folder together when moving it.

PDF and Office previews show the pages actually sent to OCR. Office originals
are downloadable; previews follow their rendered print layout. If a preview is
unavailable, the captured original and OCR text remain available. Report display
problems do not discard successfully extracted text.

The summary lists failed files and unsupported extensions. Review these counts
before treating a run as complete.

Office files render through LibreOffice with macros disabled. Password-protected
or corrupt documents may fail. Spreadsheet OCR follows print layouts, which may
exclude hidden sheets or cells outside print areas. Review important fields
against the original; OCR can omit or misread text and does not reconstruct tables.

Requires a Linux NVIDIA CUDA node with at least 48 GiB GPU memory, including DGX
Spark. First use prepares the model image, CUDA extension and multilingual weights;
later runs reuse the runtime cache. Inference stays on the selected node.

After updating this blueprint, reprepare the co-worker so its saved definition
uses the new model image and source-folder settings. Chat questions do not start
runs. Use `get_run_status` and `get_run_results` to inspect observed completion.
