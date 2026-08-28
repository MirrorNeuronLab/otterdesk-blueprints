from domain.comparison import analyze_total_cost

from ._shared import create_domain_agent


run = create_domain_agent("purchase_total_cost_analyst", analyze_total_cost)
