# NVIDIA OCR

`mirrorneuron-nvidia-ocr-skill` (`mn_nvidia_ocr_skill`) extracts complete text,
confidence scores and normalized bounding boxes using
[NVIDIA Nemotron OCR v2](https://huggingface.co/nvidia/nemotron-ocr-v2), pinned to
`0e83e83f17943524b90afa6c0fd82ac2bc1a40ca`, multilingual variant.

```python
from mn_nvidia_ocr_skill import NvidiaOcrClient

result = NvidiaOcrClient().ocr_path("/authorized/input/scan.pdf")
for page in result["pages"]:
    print(page["page_number"], page["text"])
```

Install the package with pip. Ordinary installation requires neither CUDA nor
model weights. Linux amd64, Python 3.12, NVIDIA CUDA and a prepared model image
are required by the model service. The default recipe declares 48 GiB of GPU
memory. The supplied Dockerfile uses NVIDIA's PyTorch CUDA development image,
installs pinned upstream code with `--no-build-isolation`, and downloads no
checkpoint weights while building. During first SDK-managed startup, it compiles
the C++/CUDA extension natively for the selected GPU and caches that binary.
See [runtime setup](references/runtime.md) for building and declaring that image.

The SDK owns lazy model preparation, routing, node selection, caching and lifecycle.
Client construction and catalog listing have no installation side effects. The
first valid request prepares the model through the SDK; subsequent requests reuse
its binding and cache. Model weights are cached in the runtime-owned volume.
Neither package code nor blueprint hooks invoke Docker or install Python packages.

Supported inputs: PNG, JPEG, single-frame TIFF, BMP, WebP and PDF. Limits: 32 MiB
per file, 50 PDF pages, 25 million pixels per image/page, 10,000 total regions,
4 MiB extracted text and 8 MiB JSON output. Merge granularity is `paragraph`,
`sentence` or `word`. PDF pages render sequentially at 144 DPI with bounded
dimensions. Password-protected/corrupt PDFs and multi-frame images are rejected.
The output schema and immutable model provenance are exposed as `RESULT_SCHEMA`,
`SOURCE_MODEL` and `MODEL_REVISION`.

Results preserve model reading order and report empty pages. Confidence is the
model's score, not a calibrated correctness probability. OCR can omit or misread
text, tables, handwriting and unusual layouts; review critical fields against the
source. This skill transcribes text rather than reconstructing table semantics.

Run deterministic checks from the `mn-skills` root:

```bash
python -m pytest nvidia_ocr_skill/tests -q
python3 scripts/sync_agent_skills.py --check
```

GPU inference is separately qualified by the opt-in `e2e` test. Default tests
inject the model and downloader; they do not establish CUDA build or OCR quality.
Upstream model weights use NVIDIA's license; upstream code and third-party
components retain their own notices in the built image.
