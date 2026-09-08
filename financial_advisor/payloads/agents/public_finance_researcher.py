from domain.research import step_public_finance_researcher
from ._shared import create_domain_agent

run = create_domain_agent("public_finance_researcher", step_public_finance_researcher)

