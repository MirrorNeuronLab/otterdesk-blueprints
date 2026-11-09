"""OCR format policy and immutable input preparation for a recursive batch."""

import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError

from mn_folder_files_skill import ScanLimits, scan_folder
from mn_nvidia_ocr_skill import detect_document_suffix
from mn_nvidia_ocr_skill.contracts import (
    MAX_INPUT_BYTES,
    MAX_PAGES,
    MAX_PIXELS,
    SUFFIXES,
)
from mn_sdk.blueprint.hooks import fingerprint
from mn_sdk.blueprint.outputs import capture_file, materialize_file

from .office import DocumentInputError, render_office

OFFICE_SUFFIXES = {
    ".doc",
    ".docx",
    ".docm",
    ".odt",
    ".rtf",
    ".ppt",
    ".pptx",
    ".pptm",
    ".pps",
    ".ppsx",
    ".odp",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".xlsb",
    ".ods",
}


def snapshot_folder(block, folder):
    inventory = scan_folder(
        folder,
        suffixes=SUFFIXES | OFFICE_SUFFIXES,
        check=block.check,
        limits=ScanLimits(max_file_bytes=MAX_INPUT_BYTES),
    )
    if not inventory.files:
        raise ValueError("Source folder contains no supported documents")
    records = []
    total_bytes = 0
    for item in inventory.files:
        block.check()
        ref = capture_file(block, item.path, key=item.relative_path)
        info = block.store.read(ref)
        total_bytes += info["size_bytes"]
        if (
            info["size_bytes"] > MAX_INPUT_BYTES
            or total_bytes > ScanLimits().max_total_bytes
        ):
            raise ValueError("Captured documents exceed the folder byte limits")
        records.append(
            {
                "source": item.relative_path,
                "source_sha256": info["sha256"],
                "size_bytes": info["size_bytes"],
                "file": ref.to_dict(),
            }
        )
    return {
        "files": records,
        "skipped": [
            {"source": item.relative_path, "reason": "unsupported_format"}
            for item in inventory.excluded
        ],
    }


def validate_document(data, suffix):
    """Reject corrupt/oversized pages before starting any GPU work."""
    try:
        if suffix == ".pdf":
            with pdfium.PdfDocument(data) as document:
                if not 0 < len(document) <= MAX_PAGES:
                    raise DocumentInputError("PDF must contain between 1 and 50 pages")
        else:
            with Image.open(io.BytesIO(data)) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise DocumentInputError(
                        "Multi-frame images are unsupported; use a PDF"
                    )
                if not 0 < image.width * image.height <= MAX_PIXELS:
                    raise DocumentInputError("Image exceeds 25 million pixels")
                image.load()
    except DocumentInputError:
        raise
    except (
        pdfium.PdfiumError,
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ):
        raise DocumentInputError(
            "Document is corrupt, encrypted or unsupported"
        ) from None


def prepare_document(block, item):
    suffix = Path(item["source"]).suffix.lower()
    source = materialize_file(
        block,
        item["file"],
        path=block.root + "/inputs/" + fingerprint(item["source"]) + suffix,
    )
    if suffix in OFFICE_SUFFIXES:
        data = render_office(source, check=block.check, max_bytes=MAX_INPUT_BYTES)
        suffix = ".pdf"
        ref = block.store.commit_bytes(
            block.root + "/rendered/" + fingerprint(item["source"]) + ".pdf",
            data,
            kind="ocr_rendered_pdf",
        ).to_dict()
        ocr_hash = ref["sha256"]
    else:
        data = source.read_bytes()
        try:
            suffix = detect_document_suffix(data)
        except ValueError:
            raise DocumentInputError(
                "Document signature is invalid or unsupported"
            ) from None
        ref, ocr_hash = item["file"], item["source_sha256"]
    validate_document(data, suffix)
    return {"document": ref, "suffix": suffix, "input_sha256": ocr_hash}
