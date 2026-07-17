from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("cash_flow_llm_analyst", legacy.step_cash_flow_llm_analyst)

