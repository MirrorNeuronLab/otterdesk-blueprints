from domain.preflight import assess_evidence_coverage

from ._shared import create_domain_agent


run = create_domain_agent("research_evidence_reviewer", assess_evidence_coverage)
