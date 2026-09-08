from domain.intake import step_financial_document_reader
from ._shared import create_domain_agent

run = create_domain_agent("financial_document_reader", step_financial_document_reader)

