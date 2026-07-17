from domain.reporting import publish_packet
from ._shared import create_domain_agent
run = create_domain_agent("verify_and_publish_packet", publish_packet)
