from domain.evidence import prepare_evidence

from ._shared import create_domain_agent


run = create_domain_agent("research_evidence_curator", prepare_evidence)
