from domain.workers import run_content_studio_director

from ._shared import create_domain_agent


run = create_domain_agent("bibblio_content_studio_director", run_content_studio_director)

