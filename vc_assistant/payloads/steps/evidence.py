from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from agents.claim_normalizer import run_claim_normalizer_step
from agents.document_evidence_extractor import run_document_evidence_extractor_step

from ._shared import execute


OPERATIONS = {
    "extract": run_document_evidence_extractor_step,
    "normalize": run_claim_normalizer_step,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        handler = OPERATIONS[operation]
    except KeyError as exc:
        raise ValueError(f"unknown VC evidence operation: {operation}") from exc
    return execute(context, handler, **options)
