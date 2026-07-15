from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.claim_normalizer import run_claim_normalizer
from agents.document_evidence_extractor import run_document_evidence_extractor

from ._shared import compose


def prepare_company_evidence(ctx, *, llm_client=None):
    extracted = run_document_evidence_extractor(ctx, llm_client=llm_client)
    normalized = run_claim_normalizer(ctx, llm_client=llm_client)
    return {**extracted, **normalized}


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "prepare": prepare_company_evidence,
            },
            label="VC evidence operation",
        )
    )
)
