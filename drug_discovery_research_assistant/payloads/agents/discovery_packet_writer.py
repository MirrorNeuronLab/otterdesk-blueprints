from domain.reporting import publish_ranking

from ._shared import create_domain_agent


run = create_domain_agent("discovery_packet_writer", publish_ranking)
