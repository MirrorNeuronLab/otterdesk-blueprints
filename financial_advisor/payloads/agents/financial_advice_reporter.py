from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("financial_advice_reporter", legacy.step_financial_advice_reporter)

