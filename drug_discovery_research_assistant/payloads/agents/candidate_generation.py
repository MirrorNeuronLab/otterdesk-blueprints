from domain.service import run_discovery_service
from ._shared import create_domain_agent
run = create_domain_agent("candidate_generation", run_discovery_service)
