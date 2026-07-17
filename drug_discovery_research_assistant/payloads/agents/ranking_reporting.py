from drug_discovery_domain.operations import publish_ranking
from ._shared import create_domain_agent
run = create_domain_agent("ranking_reporting", publish_ranking)

