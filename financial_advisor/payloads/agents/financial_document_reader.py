from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("financial_document_reader", workflow.step_financial_document_reader)

