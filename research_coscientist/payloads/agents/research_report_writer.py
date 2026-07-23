from domain.reporting import publish_packet

from ._shared import create_domain_agent


run = create_domain_agent("research_report_writer", publish_packet)
