# NVIDIA OCR

Extract text and page regions from one image or PDF using NVIDIA Nemotron OCR v2.
The coworker requires one NVIDIA CUDA GPU with at least 48 GiB memory on Linux
amd64. The default model is the pinned multilingual v2 checkpoint.

The workflow has one stock native-computation step. It captures the document,
calls the SDK-managed OCR service, validates provenance and writes `ocr_result.json`,
`text.txt` and `document.md` before returning bounded artifact references.
The SDK handles admission, model preparation, routing, caching and result delivery.

From the catalog root:

```bash
mn blueprint run ./nvidia_ocr --set inputs.payload.document_file=/absolute/path/scan.pdf
```

Or select the bundled synthetic `examples/sample.pdf` in setup. It contains the
strings `NVIDIA OCR sample` and `Invoice total: 42.00 USD`; these are expected
source text, not a recorded model result. The input accepts up to 32 MiB, 50 PDF
pages and 25 million pixels per page; animated/multi-frame images fail explicitly.
Paragraph merging is the default; `word` and `sentence` are optional.

The model recipe pins the published `homerquan/nvidia-ocr` image by SHA-256.
The SDK pulls it automatically on first required OCR use. Workers have a separate
lightweight Python 3.12 image. Model rebuild sources are in `payloads/model/`;
use `payloads/` as the model Docker build context.

The source skill is staged under `payloads/skills/nvidia_ocr_skill` from `mn-skills`;
make reusable changes there and regenerate that snapshot. Local mode uses declared
sibling packages (`MN_USE_LOCAL_SKILLS=1`). Binary distribution needs the declared
Python skill release in the package registry; the model image is already public.

Image preparation installs pinned upstream source without weights. First managed
startup compiles the CUDA extension natively for the actual GPU and caches it.
Only the first valid OCR request starts the model and downloads its pinned
multilingual checkpoints. The runtime's model cache persists across runs; image
and model work reuse this Job's GPU allocation. Build access needs NVIDIA's
registry, Hugging Face and Python indexes; document bytes go only to the managed
execution node. OCR can omit text and confidence is not calibrated accuracy.

```bash
synapsy verify ./nvidia_ocr --workspace /path/to/mirror-neuron-set --compile --python /path/to/runtime/python
python -m pytest nvidia_ocr/tests -q
```

Authored using Synapse's concrete-plan `synapsy create --plan` path. Offline
tests cover compiled dispatch, source integrity, publication, replay and failure.
Static checks and SDK compilation do not qualify a CUDA build or OCR quality.

Sandbox boundary: the stock Docker worker handles staged documents only. The
independent SDK-managed model container runs the pinned CUDA build script once
for its GPU, with a finite deadline and no document-derived command arguments.
It caches only its model weights and compiled extension. The worker and model
never execute source document text or accept operator-provided shell commands.
