from domain.intake import resolve_source

from ._shared import create_domain_agent

run = create_domain_agent("source_intake_analyst", resolve_source)
