from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("cash_flow_llm_analyst", workflow.step_cash_flow_llm_analyst)

