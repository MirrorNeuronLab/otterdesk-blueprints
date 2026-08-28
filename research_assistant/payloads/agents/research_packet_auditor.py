from domain.verification import audit_packet

from ._shared import create_domain_agent


run = create_domain_agent("research_packet_auditor", audit_packet)
