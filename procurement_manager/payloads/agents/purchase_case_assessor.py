"""Evaluate one selected procurement case document without external actions."""
from domain.case_packet import assess_procurement_case

from ._shared import create_domain_agent


run = create_domain_agent(
    "purchase_case_assessor", assess_procurement_case,
    additional_artifact=("procurement_case_packet", "workflow_state/procurement_case_packet.json"),
)
