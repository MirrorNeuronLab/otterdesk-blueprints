from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("tax_document_router", legacy.step_tax_document_router)

