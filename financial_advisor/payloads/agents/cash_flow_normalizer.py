from domain.cash_flow import step_cash_flow_normalizer
from ._shared import create_domain_agent

run = create_domain_agent("cash_flow_normalizer", step_cash_flow_normalizer)

