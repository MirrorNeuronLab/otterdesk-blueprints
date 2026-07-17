from domain.intake import step_bank_statement_extractor
from ._shared import create_domain_agent

run = create_domain_agent("bank_statement_extractor", step_bank_statement_extractor)

