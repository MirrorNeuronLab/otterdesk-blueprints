from domain.review import reconcile_evidence
from ._shared import create_domain_agent
run = create_domain_agent("legal_evidence_reconciler", reconcile_evidence)

