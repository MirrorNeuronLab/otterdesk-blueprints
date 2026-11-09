"""Raster previews of the exact document sent to OCR; never execute originals."""

from contextlib import closing
import io
import math

import pypdfium2 as pdfium
from PIL import Image

MAX_EDGE = 1600
MAX_PREVIEW_BYTES = 8 * 1024**2


def _png(image):
    image.thumbnail((MAX_EDGE, MAX_EDGE))
    output = io.BytesIO()
    image.save(output, format="PNG")
    data = output.getvalue()
    if len(data) > MAX_PREVIEW_BYTES:
        raise ValueError("Page preview exceeds its byte limit")
    return data


def page_previews(data, suffix, *, check):
    if suffix == ".pdf":
        with pdfium.PdfDocument(data) as document:
            for index in range(len(document)):
                check()
                with closing(document[index]) as page:
                    width, height = page.get_size()
                    if not all(
                        math.isfinite(value) and value > 0 for value in (width, height)
                    ):
                        raise ValueError("Invalid preview page dimensions")
                    with closing(
                        page.render(scale=min(2, MAX_EDGE / max(width, height)))
                    ) as bitmap:
                        with bitmap.to_pil().convert("RGB") as image:
                            yield index + 1, _png(image)
    else:
        check()
        with Image.open(io.BytesIO(data)) as source, source.convert("RGB") as image:
            yield 1, _png(image)
