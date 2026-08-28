from domain.continuous_service import run_discovery_service

from ._shared import create_domain_agent


run = create_domain_agent("discovery_service_operator", run_discovery_service)
