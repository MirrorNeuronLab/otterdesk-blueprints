from financial_domain import legacy
from ._shared import create_domain_agent

run = create_domain_agent("portfolio_market_data_loader", legacy.step_portfolio_market_data_loader)

