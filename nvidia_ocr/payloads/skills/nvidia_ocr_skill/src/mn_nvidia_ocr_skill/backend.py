"""Model-service internals. CUDA imports and checkpoint downloads stay lazy."""

from __future__ import annotations

import io
import math
from contextlib import closing
from pathlib import Path

from .contracts import (
    MAX_PAGES,
    MAX_PIXELS,
    MAX_REGIONS,
    MAX_TEXT_BYTES,
    MODEL_REVISION,
    SOURCE_MODEL,
    source_hash,
    validate_input,
    validate_result,
)

CHECKPOINT_FILES = (
    "detector.pth",
    "recognizer.pth",
    "relational.pth",
    "charset.txt",
    "model_config.json",
)


def load_pipeline():
    import platform

    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeError("Nemotron OCR requires Linux amd64 and NVIDIA CUDA")
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "Nemotron OCR requires NVIDIA CUDA; CPU fallback is unsupported"
        )
    from huggingface_hub import snapshot_download
    from nemotron_ocr.inference.pipeline_v2 import NemotronOCRV2

    root = (
        Path(
            snapshot_download(
                repo_id=SOURCE_MODEL,
                revision=MODEL_REVISION,
                allow_patterns=[f"v2_multilingual/{name}" for name in CHECKPOINT_FILES],
                max_workers=2,
            )
        )
        / "v2_multilingual"
    )
    if not all((root / name).is_file() for name in CHECKPOINT_FILES):
        # Do not let the upstream loader silently resolve an incomplete folder at main.
        raise RuntimeError("Nemotron OCR checkpoint cache is incomplete")
    return NemotronOCRV2(model_dir=str(root), detector_max_batch_size=1)


def _image(data: bytes):
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    try:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("Multi-frame images are unsupported; use a PDF")
        if not 0 < image.width * image.height <= MAX_PIXELS:
            raise ValueError("OCR image exceeds 25 million pixels")
        image.load()
        return image.convert("RGB")
    finally:
        image.close()


def _number(value) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("OCR model returned a non-finite number")
    return float(value)


def normalize_regions(predictions) -> list[dict]:
    if not isinstance(predictions, list) or len(predictions) > MAX_REGIONS:
        raise ValueError("OCR model returned invalid or excessive regions")
    regions = []
    text_size = 0
    for prediction in predictions:
        if not isinstance(prediction, dict) or not isinstance(
            prediction.get("text"), str
        ):
            raise TypeError("OCR model returned an invalid text region")
        confidence = _number(prediction.get("confidence"))
        if not 0 <= confidence <= 1:
            raise ValueError("OCR model returned invalid confidence")
        left, top, right, bottom = [
            _number(prediction.get(key)) for key in ("left", "lower", "right", "upper")
        ]
        if left > right or top > bottom:
            raise ValueError("OCR model returned an inverted bounding box")
        text_size += len(prediction["text"].encode())
        if text_size > MAX_TEXT_BYTES:
            raise ValueError("OCR text exceeds its limit")
        regions.append(
            {
                "text": prediction["text"],
                "confidence": confidence,
                "bbox": [
                    max(0.0, min(1.0, value)) for value in (left, top, right, bottom)
                ],
            }
        )
    return regions


class NemotronOcrBackend:
    def __init__(self, *, pipeline_factory=load_pipeline):
        self._factory = pipeline_factory
        self._pipeline = None

    def prepare(self):
        if self._pipeline is None:
            self._pipeline = self._factory()
        return self

    def extract(
        self, data: bytes, *, suffix: str, merge_level: str = "paragraph"
    ) -> dict:
        suffix = validate_input(data, suffix, merge_level)
        pages = []

        def recognize(image):
            # Validate/decode a complete page before starting or downloading a model.
            self.prepare()
            import numpy as np

            regions = normalize_regions(
                self._pipeline(np.array(image), merge_level=merge_level)
            )
            page = {
                "page_number": len(pages) + 1,
                "width": image.width,
                "height": image.height,
                "text": "\n".join(region["text"] for region in regions),
                "regions": regions,
            }
            if (
                sum(len(item["regions"]) for item in pages) + len(regions) > MAX_REGIONS
                or sum(len(item["text"].encode()) for item in pages)
                + len(page["text"].encode())
                > MAX_TEXT_BYTES
            ):
                raise ValueError("OCR document exceeds region or text limits")
            pages.append(page)

        if suffix == ".pdf":
            import pypdfium2 as pdfium

            with pdfium.PdfDocument(data) as document:
                if not 0 < len(document) <= MAX_PAGES:
                    raise ValueError("OCR PDF must contain between 1 and 50 pages")
                for index in range(len(document)):
                    with closing(document[index]) as page:
                        width, height = page.get_size()
                        if not all(
                            math.isfinite(value) and value > 0
                            for value in (width, height)
                        ):
                            raise ValueError("Invalid PDF page dimensions")
                        # Bound raster allocation before invoking PDFium.
                        scale = min(2.0, math.sqrt(MAX_PIXELS / (width * height)))
                        while (
                            math.ceil(width * scale) * math.ceil(height * scale)
                            > MAX_PIXELS
                        ):
                            scale *= 0.99
                        with closing(page.render(scale=scale)) as bitmap:
                            image = bitmap.to_pil().convert("RGB")
                            try:
                                recognize(image)
                            finally:
                                image.close()
        else:
            with _image(data) as image:
                recognize(image)
        result = {
            "schema": "mn.nvidia_ocr.result.v1",
            "source_model": SOURCE_MODEL,
            "model_revision": MODEL_REVISION,
            "variant": "v2_multilingual",
            "input_sha256": source_hash(data),
            "merge_level": merge_level,
            "pages": pages,
            "warnings": [
                f"no_text_detected:page_{page['page_number']}"
                for page in pages
                if not page["text"].strip()
            ],
        }
        return validate_result(result)
