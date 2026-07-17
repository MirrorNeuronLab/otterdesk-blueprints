from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("advisor_evidence_reconciler", legacy.step_advisor_evidence_reconciler)

