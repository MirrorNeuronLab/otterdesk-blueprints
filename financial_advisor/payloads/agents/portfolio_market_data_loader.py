from domain.portfolio import step_portfolio_market_data_loader
from ._shared import create_domain_agent

run = create_domain_agent("portfolio_market_data_loader", step_portfolio_market_data_loader)

