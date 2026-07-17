from research_domain.operations import prepare_evidence
from ._shared import create_domain_agent
run = create_domain_agent("retrieve_and_evaluate_evidence", prepare_evidence)

