from domain.workers import run_growth_lead

from ._shared import create_domain_agent


run = create_domain_agent("bibblio_growth_lead", run_growth_lead)

