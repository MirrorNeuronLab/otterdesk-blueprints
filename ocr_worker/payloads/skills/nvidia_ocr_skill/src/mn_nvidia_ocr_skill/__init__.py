"""NVIDIA OCR; importing this module performs no model or runtime preparation."""

from .client import NvidiaOcrClient
from .contracts import (
    MODEL_ID,
    MODEL_IMAGE,
    MODEL_REVISION,
    RESULT_SCHEMA,
    SOURCE_MODEL,
    build_ocr_request,
    detect_document_suffix,
    runtime_model_spec,
    validate_result,
)

__all__ = [
    "MODEL_ID",
    "MODEL_IMAGE",
    "MODEL_REVISION",
    "RESULT_SCHEMA",
    "SOURCE_MODEL",
    "NvidiaOcrClient",
    "build_ocr_request",
    "detect_document_suffix",
    "runtime_model_spec",
    "validate_result",
]
