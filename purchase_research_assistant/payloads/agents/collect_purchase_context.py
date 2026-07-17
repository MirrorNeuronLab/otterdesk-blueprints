from purchase_domain.operations import collect_context
from ._shared import create_domain_agent
run = create_domain_agent("collect_purchase_context", collect_context)

