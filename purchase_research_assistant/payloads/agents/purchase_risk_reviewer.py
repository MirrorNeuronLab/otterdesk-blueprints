from domain.comparison import review_purchase_risks

from ._shared import create_domain_agent


run = create_domain_agent("purchase_risk_reviewer", review_purchase_risks)
