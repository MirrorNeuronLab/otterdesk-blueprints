from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("bank_statement_extractor", legacy.step_bank_statement_extractor)

