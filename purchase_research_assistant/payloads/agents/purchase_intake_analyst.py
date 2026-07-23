from domain.intake import collect_context

from ._shared import create_domain_agent


run = create_domain_agent("purchase_intake_analyst", collect_context)
