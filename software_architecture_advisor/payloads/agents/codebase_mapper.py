from domain.mapping import map_architecture

from ._shared import create_domain_agent

run = create_domain_agent("codebase_mapper", map_architecture)
