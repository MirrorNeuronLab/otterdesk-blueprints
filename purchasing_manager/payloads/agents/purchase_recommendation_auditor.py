from domain.comparison import audit_recommendation

from ._shared import create_domain_agent


run = create_domain_agent("purchase_recommendation_auditor", audit_recommendation)
