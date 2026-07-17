from domain.reporting import publish_report
from ._shared import create_domain_agent
run = create_domain_agent("write_purchase_report", publish_report)
