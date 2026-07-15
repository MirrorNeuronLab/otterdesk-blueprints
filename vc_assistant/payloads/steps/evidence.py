from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.claim_normalizer import run_claim_normalizer_step
from agents.document_evidence_extractor import run_document_evidence_extractor_step

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "extract": run_document_evidence_extractor_step,
                "normalize": run_claim_normalizer_step,
            },
            label="VC evidence operation",
        )
    )
)
