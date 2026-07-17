from legal_domain.operations import audit_review
from ._shared import create_domain_agent
run = create_domain_agent("legal_review_auditor", audit_review)

