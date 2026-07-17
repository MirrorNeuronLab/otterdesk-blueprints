from financial_domain import workflow
from ._shared import create_domain_agent

run = create_domain_agent("portfolio_context_loader", workflow.step_portfolio_context_loader)

