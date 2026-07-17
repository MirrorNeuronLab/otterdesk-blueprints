from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("bank_statement_extractor", workflow.step_bank_statement_extractor)

