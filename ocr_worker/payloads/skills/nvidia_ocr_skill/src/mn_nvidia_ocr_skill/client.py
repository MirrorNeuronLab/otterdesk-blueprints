"""Lazy managed OCR requests; no Docker CLI or package installation."""

from __future__ import annotations

import math
from pathlib import Path

from .contracts import (
    MAX_INPUT_BYTES,
    MODEL_ID,
    MODEL_IMAGE,
    RESULT_SCHEMA,
    build_ocr_request,
    runtime_model_spec,
    source_hash,
    validate_result,
)


class NvidiaOcrClient:
    def __init__(self, *, image: str = MODEL_IMAGE, timeout_seconds: float = 900):
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 3600
        ):
            raise ValueError("OCR timeout must be finite and within one hour")
        self.model_spec = runtime_model_spec(image=image)
        self.timeout_seconds = timeout_seconds

    def ocr_path(self, path: str | Path, *, merge_level: str = "paragraph") -> dict:
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise ValueError("OCR input must be an authorized regular file")
        with source.open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
        request = build_ocr_request(data, suffix=source.suffix, merge_level=merge_level)
        from mn_sdk.blueprint.models import runtime_model_json_request

        result = runtime_model_json_request(
            "ocr",
            MODEL_ID,
            request["path"],
            request["payload"],
            provider="docker_model_runner",
            backend="docker",
            model_spec=self.model_spec,
            response_schema=RESULT_SCHEMA,
            timeout_seconds=self.timeout_seconds,
            num_retries=0,
        )
        result = validate_result(result, input_sha256=source_hash(data))
        if result["merge_level"] != merge_level:
            raise ValueError("OCR result merge level does not match the request")
        return result
