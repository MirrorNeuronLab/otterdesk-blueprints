from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("public_finance_researcher", workflow.step_public_finance_researcher)

