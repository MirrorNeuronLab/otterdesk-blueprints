from domain.case_packet import publish_verified_case

from ._shared import create_domain_agent


run = create_domain_agent("purchase_report_writer", publish_verified_case)
