from domain.workers import run_parent_lifecycle_director

from ._shared import create_domain_agent


run = create_domain_agent("bibblio_parent_lifecycle_director", run_parent_lifecycle_director)

