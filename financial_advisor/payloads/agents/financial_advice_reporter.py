from domain.advice import step_financial_advice_reporter
from ._shared import create_domain_agent

run = create_domain_agent("financial_advice_reporter", step_financial_advice_reporter)

