from domain.portfolio import step_portfolio_context_loader
from ._shared import create_domain_agent

run = create_domain_agent("portfolio_context_loader", step_portfolio_context_loader)

