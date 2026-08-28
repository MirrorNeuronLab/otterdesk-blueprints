from domain.reporting import publish_advice

from ._shared import create_domain_agent

run = create_domain_agent("architecture_artifact_publisher", publish_advice)
