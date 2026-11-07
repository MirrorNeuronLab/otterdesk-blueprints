"""Portable request/result contracts and a data-only managed model recipe."""

from __future__ import annotations

import base64
import copy
import hashlib
import json

SOURCE_MODEL = "nvidia/nemotron-ocr-v2"
MODEL_REVISION = "0e83e83f17943524b90afa6c0fd82ac2bc1a40ca"
MODEL_ID = "nvidia-nemotron-ocr-v2:0.1.0"
MODEL_IMAGE = "docker.io/homerquan/nvidia-ocr:0.1.0"
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024
MAX_PAGES = 50
MAX_PIXELS = 25_000_000
MAX_REGIONS = 10_000
MERGE_LEVELS = {"word", "sentence", "paragraph"}
SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

REGION_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "maxLength": MAX_TEXT_BYTES},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "bbox": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
    "required": ["text", "confidence", "bbox"],
    "additionalProperties": False,
}
PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "page_number": {"type": "integer", "minimum": 1, "maximum": MAX_PAGES},
        "width": {"type": "integer", "minimum": 1, "maximum": MAX_PIXELS},
        "height": {"type": "integer", "minimum": 1, "maximum": MAX_PIXELS},
        "text": {"type": "string", "maxLength": MAX_TEXT_BYTES},
        "regions": {"type": "array", "maxItems": MAX_REGIONS, "items": REGION_SCHEMA},
    },
    "required": ["page_number", "width", "height", "text", "regions"],
    "additionalProperties": False,
}
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "schema": {"const": "mn.nvidia_ocr.result.v1"},
        "source_model": {"const": SOURCE_MODEL},
        "model_revision": {"const": MODEL_REVISION},
        "variant": {"const": "v2_multilingual"},
        "input_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "merge_level": {"enum": sorted(MERGE_LEVELS)},
        "pages": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_PAGES,
            "items": PAGE_SCHEMA,
        },
        "warnings": {
            "type": "array",
            "maxItems": MAX_PAGES,
            "items": {"type": "string", "maxLength": 100},
        },
    },
    "required": [
        "schema",
        "source_model",
        "model_revision",
        "variant",
        "input_sha256",
        "merge_level",
        "pages",
        "warnings",
    ],
    "additionalProperties": False,
}


def runtime_model_spec(*, image: str = MODEL_IMAGE) -> dict:
    """Return a fresh SDK-owned Docker/HTTP JSON recipe, without side effects."""
    return {
        "id": MODEL_ID,
        "model": MODEL_ID,
        "name": "NVIDIA Nemotron OCR v2",
        "source": "docker",
        "provider": "docker_model_runner",
        "backend": "docker",
        "backends": ["docker"],
        "protocol": "http_json",
        "model_type": "ocr",
        "input_modalities": ["image"],
        "requirements": {"min_vram_gb": 48, "required_capabilities": ["cuda"]},
        "docker": {
            "image": image,
            "port": 30084,
            "container_port": 8000,
            "gpus": "all",
            "shm_size": "8g",
            "api_path": "/v1",
            "ready_path": "/health",
            "ready_timeout": 3600,
            "cache_path": "/cache",
            "environment": {
                "HF_HOME": "/cache",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "DO_NOT_TRACK": "1",
            },
        },
    }


def validate_input(data: bytes, suffix: str, merge_level: str) -> str:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_INPUT_BYTES:
        raise ValueError("OCR input must be nonempty bytes within 32 MiB")
    if not isinstance(suffix, str) or suffix.lower() not in SUFFIXES:
        raise ValueError("Unsupported OCR document format")
    if not isinstance(merge_level, str) or merge_level not in MERGE_LEVELS:
        raise ValueError("merge_level must be word, sentence or paragraph")
    suffix = suffix.lower()
    signatures = {
        ".pdf": data.startswith(b"%PDF-"),
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".tif": data.startswith((b"II*\x00", b"MM\x00*")),
        ".tiff": data.startswith((b"II*\x00", b"MM\x00*")),
        ".bmp": data.startswith(b"BM"),
        ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if not signatures[suffix]:
        raise ValueError("OCR input signature does not match its document format")
    return suffix


def build_ocr_request(
    data: bytes, *, suffix: str, merge_level: str = "paragraph"
) -> dict:
    suffix = validate_input(data, suffix, merge_level)
    return {
        "path": "/ocr",
        "payload": {
            "document_base64": base64.b64encode(data).decode("ascii"),
            "suffix": suffix,
            "merge_level": merge_level,
        },
    }


def detect_document_suffix(data: bytes) -> str:
    """Detect supported document bytes after a caller's staging renamed the file."""
    for suffix in (".pdf", ".png", ".jpg", ".tif", ".bmp", ".webp"):
        try:
            return validate_input(data, suffix, "paragraph")
        except ValueError:
            continue
    raise ValueError("Unsupported or invalid OCR document")


def validate_result(result: dict, *, input_sha256: str | None = None) -> dict:
    """Reject malformed/incomplete responses; preserve complete model text."""
    from jsonschema import Draft202012Validator

    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("OCR result exceeds 8 MiB")
    Draft202012Validator(RESULT_SCHEMA).validate(result)
    if input_sha256 is not None and result["input_sha256"] != input_sha256:
        raise ValueError("OCR result does not match its source document")
    region_count, text_bytes = 0, 0
    for number, page in enumerate(result["pages"], 1):
        if page["page_number"] != number or page["width"] * page["height"] > MAX_PIXELS:
            raise ValueError("Invalid OCR page order or dimensions")
        if page["text"] != "\n".join(region["text"] for region in page["regions"]):
            raise ValueError("OCR page text does not match its regions")
        for region in page["regions"]:
            left, top, right, bottom = region["bbox"]
            if left > right or top > bottom:
                raise ValueError("Invalid OCR bounding box ordering")
        region_count += len(page["regions"])
        text_bytes += len(page["text"].encode())
    if region_count > MAX_REGIONS or text_bytes > MAX_TEXT_BYTES:
        raise ValueError("OCR result exceeds region or text limits")
    return copy.deepcopy(result)


def source_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
