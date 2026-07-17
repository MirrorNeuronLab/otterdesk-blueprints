from domain.portfolio import step_portfolio_risk_engine
from ._shared import create_domain_agent

run = create_domain_agent("portfolio_risk_engine", step_portfolio_risk_engine)

