from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("public_finance_researcher", legacy.step_public_finance_researcher)

