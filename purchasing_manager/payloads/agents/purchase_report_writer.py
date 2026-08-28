from domain.reporting import publish_report

from ._shared import create_domain_agent


run = create_domain_agent("purchase_report_writer", publish_report)
