from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("financial_document_reader", legacy.step_financial_document_reader)

