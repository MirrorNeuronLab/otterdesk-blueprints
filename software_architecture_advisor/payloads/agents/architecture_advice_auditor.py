from domain.audit import audit_advice

from ._shared import create_domain_agent

run = create_domain_agent("architecture_advice_auditor", audit_advice)
