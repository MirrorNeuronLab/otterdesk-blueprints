from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("portfolio_context_loader", legacy.step_portfolio_context_loader)

