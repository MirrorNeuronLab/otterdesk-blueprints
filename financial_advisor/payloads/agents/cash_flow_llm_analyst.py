from domain.cash_flow import step_cash_flow_llm_analyst
from ._shared import create_domain_agent

run = create_domain_agent("cash_flow_llm_analyst", step_cash_flow_llm_analyst)

