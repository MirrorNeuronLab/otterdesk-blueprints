from domain.review import assess_architecture

from ._shared import create_domain_agent

run = create_domain_agent("architecture_reviewer", assess_architecture)
