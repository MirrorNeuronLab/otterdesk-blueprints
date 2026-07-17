from domain.tax import step_tax_document_router
from ._shared import create_domain_agent

run = create_domain_agent("tax_document_router", step_tax_document_router)

