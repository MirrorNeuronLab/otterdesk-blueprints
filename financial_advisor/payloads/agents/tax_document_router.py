from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("tax_document_router", workflow.step_tax_document_router)

